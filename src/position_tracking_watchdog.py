"""Independent watchdog for the Windows EXE. No third-party dependencies.

The parent owns NO booth session. The child owns the GUI, its local durable
outbox, and the normal central SMB state. A stalled GUI is forcibly restarted
WITHOUT sending END; the existing open sessions are never implicitly closed.
"""
from __future__ import annotations

import contextlib
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid


def parent_is_alive(pid: int) -> bool:
    """A GUI child exits if its supervisor is killed, avoiding orphan windows."""
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    kernel.GetExitCodeProcess.restype = ctypes.c_int
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = ctypes.c_uint()
        return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(handle)


def _log(directory: Path, message: str) -> None:
    # This is operational telemetry only; no names, AGMS or personal records.
    try:
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with (directory / "watchdog_events.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{stamp} | {message}\n")
    except OSError:
        pass


@contextlib.contextmanager
def one_watchdog_per_windows_session():
    """Prevent double-click from launching duplicate booth programs."""
    if os.name != "nt":
        yield True
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.CreateMutexW(None, False, "Local\\TDE_PositionTracking_Watchdog_202610")
    if not handle:
        raise OSError("Δεν δημιουργήθηκε κλείδωμα μοναδικής εφαρμογής.")
    already_exists = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    try:
        yield not already_exists
    finally:
        kernel.CloseHandle(handle)


def _stop_child(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    # terminate() uses Windows TerminateProcess. The SQLite outbox commits
    # independently and is reopened on next launch; active shifts stay open.
    with contextlib.suppress(OSError):
        child.terminate()
    try:
        child.wait(timeout=8)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            child.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            child.wait(timeout=5)


def supervise(
    executable: str | Path,
    heartbeat_dir: str | Path,
    *,
    child_arguments: tuple[str, ...] = ("--tde-watched-child",),
    startup_timeout: float = 90.0,
    freeze_timeout: float = 45.0,
    poll_interval: float = 1.0,
    max_restarts: int = 3,
    restart_window: float = 600.0,
) -> int:
    """Restart on GUI freeze or abnormal child exit; stop on normal exit.

    Crash-loop protection: after max_restarts in restart_window seconds,
    stop and leave a local log. Never start two child instances at once.
    """
    folder = Path(heartbeat_dir)
    folder.mkdir(parents=True, exist_ok=True)
    restarts = []
    while True:
        beat = folder / (uuid.uuid4().hex + ".heartbeat")
        cmd = [str(executable), *child_arguments, str(beat), str(os.getpid())]
        try:
            child = subprocess.Popen(cmd)
        except OSError as exc:
            _log(folder, f"child_launch_failed {type(exc).__name__}: {exc}")
            return 2
        created = time.monotonic()
        latest_beat = None
        beat_mtime = None
        reason = None
        try:
            while True:
                exit_code = child.poll()
                if exit_code is not None:
                    if exit_code == 0:
                        _log(folder, "normal_exit")
                        return 0
                    reason = f"child_crash_exit_code={exit_code}"
                    break
                now = time.monotonic()
                try:
                    stamped = beat.stat().st_mtime_ns
                    if stamped != beat_mtime:
                        beat_mtime = stamped
                        latest_beat = now
                except OSError:
                    pass
                if latest_beat is None and now - created > startup_timeout:
                    reason = "gui_startup_timeout"
                    break
                if latest_beat is not None and now - latest_beat > freeze_timeout:
                    reason = "gui_unresponsive_timeout"
                    break
                time.sleep(poll_interval)
        finally:
            _stop_child(child)
            with contextlib.suppress(OSError):
                beat.unlink()
        _log(folder, f"restarted_after {reason or 'unknown'}")
        now = time.monotonic()
        restarts = [t for t in restarts if now - t < restart_window]
        restarts.append(now)
        if len(restarts) > max_restarts:
            _log(folder, "too_many_restarts_manual_attention_required")
            return 3
        time.sleep(min(2.0, poll_interval))


def run_frozen_watchdog(executable: str | Path, local_root: str | Path) -> int:
    folder = Path(local_root) / "watchdog"
    with one_watchdog_per_windows_session() as allowed:
        if not allowed:
            _log(folder, "duplicate_launcher_ignored")
            return 0
        _log(folder, "watchdog_start")
        return supervise(executable, folder)

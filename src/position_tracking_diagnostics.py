"""Local bounded stall diagnostics; no service data, remote I/O or forced recovery."""
from __future__ import annotations
import ctypes
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import weakref


def process_resources() -> dict:
    result = {"threads": threading.active_count(), "cpu_seconds": time.process_time()}
    if os.name == "nt":
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel.GetCurrentProcess()
        memory = Counters(); memory.cb = ctypes.sizeof(memory)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), wintypes.DWORD]
        if psapi.GetProcessMemoryInfo(process, ctypes.byref(memory), memory.cb):
            result["rss_bytes"] = memory.WorkingSetSize
        count = wintypes.DWORD()
        kernel.GetProcessHandleCount.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
        if kernel.GetProcessHandleCount(process, ctypes.byref(count)):
            result["handles"] = count.value
    elif sys.platform.startswith("linux"):
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                result["rss_bytes"] = int(line.split()[1]) * 1024
        result["handles"] = len(list(Path("/proc/self/fd").iterdir()))
    return result


def thread_locations() -> list[dict]:
    # Never include frame locals, source lines, exception messages or full paths.
    frames = sys._current_frames()
    names = {t.ident: t.name for t in threading.enumerate()}
    return [{"thread": names.get(ident, "unknown"), "locations": [
        f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
        for frame in traceback.extract_stack(stack)[-24:]
    ]} for ident, stack in frames.items()]


class RuntimeDiagnostics:
    def __init__(self, directory: Path, *, gui_timeout=5.0, worker_timeout=45.0,
                 interval=1.0, sample_interval=30.0, max_bytes=524288, backups=3):
        self.path = Path(directory) / f"runtime-{os.getpid()}.jsonl"
        self.gui_timeout = gui_timeout; self.worker_timeout = worker_timeout
        self.interval = interval; self.sample_interval = sample_interval
        self.max_bytes = max_bytes; self.backups = backups
        self._lock = threading.Lock(); self._stop = threading.Event()
        self._last_heartbeat = time.monotonic(); self._workers = {}; self._queues = {}
        self.available = False
        self.thread = threading.Thread(target=self._run, name="TDE-diagnostics", daemon=True)
        self.thread.start()

    def heartbeat(self, workers: dict | None = None, queues: dict | None = None):
        now = time.monotonic()
        with self._lock:
            self._last_heartbeat = now
            previous = self._workers
            self._workers = {name: (token, previous[name][1] if name in previous and previous[name][0] == token else now)
                             for name, token in (workers or {}).items()}
            self._queues = dict(queues or {})

    def stop(self, *, wait=False):
        self._stop.set()
        if wait:
            self.thread.join(timeout=2)

    def _run(self):
        logger = logging.Logger(f"TDE-runtime-{os.getpid()}-{id(self)}")
        handler = None
        try:
            # Disk setup and all writes occur off Qt and only below local_root.
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            handler = RotatingFileHandler(self.path, maxBytes=self.max_bytes,
                                          backupCount=self.backups, encoding="utf-8")
            handler.handleError = lambda record: None
            logger.addHandler(handler); self.available = True
            def emit(event, **fields):
                logger.warning(json.dumps({"at_utc": datetime.now(timezone.utc).isoformat(),
                                           "event": event, **fields}, ensure_ascii=True))
            emit("session_start", pid=os.getpid())
            last_sample = 0.0; gui_stalled = False; warned_workers = set()
            while not self._stop.wait(self.interval):
                now = time.monotonic()
                with self._lock:
                    age = now - self._last_heartbeat
                    workers = {name: (token, now - started) for name, (token, started) in self._workers.items()}
                    queues = dict(self._queues)
                if age > self.gui_timeout and not gui_stalled:
                    emit("gui_stall", heartbeat_age_seconds=round(age, 3), stacks=thread_locations())
                    gui_stalled = True
                elif age <= self.gui_timeout and gui_stalled:
                    emit("gui_recovered"); gui_stalled = False
                stalled = {(name, token) for name, (token, age) in workers.items() if age > self.worker_timeout}
                if stalled - warned_workers:
                    emit("worker_stall", workers={n: round(a, 3) for n, (_, a) in workers.items()},
                         stacks=thread_locations())
                warned_workers = stalled
                if now - last_sample >= self.sample_interval:
                    try: resources = process_resources()
                    except Exception: resources = {"unavailable": True}
                    emit("sample", gui_age_seconds=round(age, 3), queues=queues,
                         workers={n: round(a, 3) for n, (_, a) in workers.items()}, **resources)
                    last_sample = now
            emit("session_stop")
        except Exception:
            # Unwritable diagnostics must not affect event persistence or launch.
            self.available = False
        finally:
            if handler is not None:
                handler.close()


def start_runtime_diagnostics(app, window, local_directory: Path):
    from PySide6.QtCore import QTimer
    diagnostics = RuntimeDiagnostics(Path(local_directory) / "diagnostics")
    reference = weakref.ref(window)
    def heartbeat():
        current = reference()
        if current is None: return
        workers = {}
        for name in ("offline", "communication", "shift", "shift_status", "agms", "position_operation", "map_mutation", "exit"):
            future = getattr(current, f"_{name}_future", None)
            if future is not None and not future.done(): workers[name] = id(future)
        queues = {}
        for name in ("network", "state", "position"):
            pool = getattr(current, f"_{name}_pool", None)
            if pool is not None: queues[name] = pool._work_queue.qsize()
        diagnostics.heartbeat(workers, queues)
    timer = QTimer(window); timer.timeout.connect(heartbeat); timer.start(500)
    app.aboutToQuit.connect(timer.stop)
    app.aboutToQuit.connect(diagnostics.stop)
    window._runtime_diagnostics_timer = timer
    window._runtime_diagnostics = diagnostics
    return diagnostics

"""Pure-process crash/hang watchdog acceptance tests; no Qt required.

The same independent supervisor runs around the frozen Windows GUI.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location("position_tracking_watchdog", ROOT / "src" / "position_tracking_watchdog.py")
WD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = WD
SPEC.loader.exec_module(WD)


def fake_worker():
    mode, state, beat, supervisor = sys.argv[2:6]
    marker = Path(state)
    heartbeat = Path(beat)
    assert WD.parent_is_alive(int(supervisor))
    if mode == "normal":
        heartbeat.touch()
        time.sleep(0.1)
        heartbeat.touch()
        raise SystemExit(0)
    if mode in ("silent-first", "freeze-first"):
        if not marker.exists():
            marker.write_text("first child", encoding="utf-8")
            if mode == "freeze-first":
                heartbeat.touch()
            time.sleep(20)  # Simulates frozen Qt GUI, no heartbeat updates.
            raise SystemExit("Supervisor did not terminate frozen child")
        heartbeat.touch()
        time.sleep(0.10)
        heartbeat.touch()
        raise SystemExit(0)
    if mode == "crash":
        raise SystemExit(19)
    raise AssertionError(mode)


if len(sys.argv) > 1 and sys.argv[1] == "--child":
    fake_worker()


def execute(mode, *, max_restarts=3):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        t0 = time.monotonic()
        result = WD.supervise(
            sys.executable, root / "watchdog",
            child_arguments=(str(THIS), "--child", mode, str(root / "once.txt")),
            startup_timeout=0.9,
            freeze_timeout=0.7,
            poll_interval=0.05,
            max_restarts=max_restarts,
            restart_window=60,
        )
        elapsed = time.monotonic() - t0
        log = (root / "watchdog" / "watchdog_events.log").read_text(encoding="utf-8")
        assert elapsed < 9, (mode, elapsed, log)
        assert not list((root / "watchdog").glob("*.heartbeat")), "Orphaned heartbeat"
        return result, log


normal, log = execute("normal")
assert normal == 0 and "normal_exit" in log and "restarted_after" not in log
print("WATCHDOG_NORMAL_EXIT: PASS")

hung_start, log = execute("silent-first")
assert hung_start == 0 and "gui_startup_timeout" in log and "normal_exit" in log, log
print("WATCHDOG_STUCK_STARTUP_AUTO_RECOVERY: PASS")

frozen, log = execute("freeze-first")
assert frozen == 0 and "gui_unresponsive_timeout" in log and "normal_exit" in log, log
print("WATCHDOG_FROZEN_GUI_AUTO_RECOVERY: PASS")

crashed, log = execute("crash", max_restarts=1)
assert crashed == 3 and "too_many_restarts_manual_attention_required" in log, log
print("WATCHDOG_CRASH_LOOP_BOUND: PASS")

assert WD.parent_is_alive(os.getpid())
assert not WD.parent_is_alive(99999999)
print("WATCHDOG_SUPERVISOR_LIVENESS: PASS")

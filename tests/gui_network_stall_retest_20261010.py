"""GUI/event-loop acceptance with artificially stalled central share.

Runs Qt offscreen on the Windows build runner. Distinct from data replay tests:
the window must still process user input while its background SMB check stalls.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

if len(sys.argv) > 1 and sys.argv[1] == "--qt-probe":
    from PySide6 import QtCore, QtWidgets
    root = Path(sys.argv[2])
    central = root / "missing_axyp_share"
    os.environ["TDE_POSITION_LOCAL_ROOT"] = str(root / "private")
    os.environ["TDE_POSITION_MACHINE_ROOT"] = str(root / "machine")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    MOD.AppConfig.load = classmethod(
        lambda cls: cls(central_root=str(central), personnel_file="", positions=[str(i) for i in range(1, 15)])
    )
    regular_is_dir = Path.is_dir

    def slow_network_directory(self):
        if str(self) == str(central):
            time.sleep(6.0)
            return False
        return regular_is_dir(self)

    Path.is_dir = slow_network_directory
    OriginalApp = QtWidgets.QApplication

    class InstrumentedApp(OriginalApp):
        def __init__(self, args):
            super().__init__(args)
            self.beats = []
            self.t0 = time.monotonic()
            self.poked = False
            self.start_enabled = False
            self.probe_timer = QtCore.QTimer(self)
            self.probe_timer.timeout.connect(lambda: self.beats.append(time.monotonic()))
            self.probe_timer.start(100)

            def poke():
                windows = [w for w in self.topLevelWidgets() if hasattr(w, "agms_input")]
                if windows:
                    window = windows[0]
                    worker = MOD.PersonnelRecord("123456", "ΑΣΤ", "TEST", "PERSON")
                    window.people = (worker,)
                    window._people_by_agms = {worker.agms: worker}
                    window.agms_input.setText(worker.agms)
                    window.position.setCurrentText("8")
                    self.start_enabled = bool(window.start_btn.isEnabled())
                    self.poked = True

            QtCore.QTimer.singleShot(750, poke)
            def finish_probe():
                # Terminate from the Qt timer itself. Python's ThreadPoolExecutor
                # atexit would otherwise wait for deliberately blocked SMB jobs,
                # obscuring whether the GUI was responsive.
                gaps = [b-a for a,b in zip(self.beats, self.beats[1:])]
                summary = {
                    "beats": len(self.beats),
                    "max_gap_s": round(max(gaps, default=0), 3),
                    "poked": self.poked,
                    "start_enabled": self.start_enabled,
                    "elapsed_s": round(time.monotonic()-self.t0, 3),
                }
                print("GUI_PROBE:" + json.dumps(summary), flush=True)
                os._exit(0)
            QtCore.QTimer.singleShot(3400, finish_probe)

    QtWidgets.QApplication = InstrumentedApp
    MOD.run(["TDE Position Tracking - test"])
    raise SystemExit("Qt event loop quit unexpectedly before responsiveness report")

with tempfile.TemporaryDirectory() as d:
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    try:
        output = subprocess.run(
            [sys.executable, "-u", str(SCRIPT), "--qt-probe", d],
            env=env, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=18,
        )
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            "GUI event loop did not emit its timed heartbeat in 18 seconds; "
            f"stdout={exc.stdout!r}; stderr={exc.stderr!r}"
        ) from exc
    assert output.returncode == 0, (output.stdout, output.stderr[-1600:])
    rows = [x for x in output.stdout.splitlines() if x.startswith("GUI_PROBE:")]
    assert len(rows) == 1, (output.stdout, output.stderr[-1600:])
    report = json.loads(rows[0].partition(":")[2])
    assert report["beats"] >= 20, report
    assert report["max_gap_s"] < 1.0, report
    assert report["poked"] is True, report
    assert report["start_enabled"] is True, report
    assert report["elapsed_s"] < 6, report
    print("GUI_NETWORK_STALL_RESPONSIVENESS: PASS", report)

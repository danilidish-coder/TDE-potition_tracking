"""Reproduce the field symptom: AGMS is recognized, but START/END remains
disabled because unchanged sync cycles reset a slow remote status lookup.

Qt is exercised on the *real MainWindow* with a 12-second artificial
remote get_active() stall and healthy periodic sync. The worker's
3-second fallback must enable START without interfering with END safety.
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
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


if len(sys.argv) > 1 and sys.argv[1] == "--qt-buttons-child":
    from PySide6 import QtCore, QtWidgets

    base = Path(sys.argv[2])
    os.environ["TDE_POSITION_LOCAL_ROOT"] = str(base / "private")
    os.environ["TDE_POSITION_MACHINE_ROOT"] = str(base / "machine")
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    central = base / "server" / "TDE_DATA"
    MOD.SharedEventStore(central)
    MOD.AppConfig.load = classmethod(lambda cls: cls(
        central_root=str(central), personnel_file="",
        positions=[str(i) for i in range(1, 15)],
    ))
    original_get_active = MOD.SharedEventStore.get_active
    def slow_get_active(self, agms):
        if agms == "99501":
            time.sleep(12.0)
        return original_get_active(self, agms)
    MOD.SharedEventStore.get_active = slow_get_active

    class InstrumentedApp(QtWidgets.QApplication):
        def __init__(self, argv):
            super().__init__(argv)
            self.window = None
            self.selected_at = None
            self.failed = None
            self.wait_started = time.monotonic()
            self.selector = QtCore.QTimer(self)
            self.selector.setInterval(120)
            self.selector.timeout.connect(self.maybe_select)
            self.selector.start()
            QtCore.QTimer.singleShot(11500, lambda: self.finish("timeout"))

        def maybe_select(self):
            if self.selected_at is not None:
                return
            candidates = [w for w in self.topLevelWidgets()
                          if hasattr(w, "agms_input") and hasattr(w, "start_btn")]
            if not candidates:
                return
            window = candidates[0]
            if window.store is None or window._last_operator_sync_signature is None:
                return
            self.window = window
            selected = MOD.PersonnelRecord("99501", "ΑΣΤ", "SURNAME", "GIVEN")
            window.people = (selected,)
            window._people_by_agms = {selected.agms: selected}
            window.position.setCurrentText("8")
            window.agms_input.setText(selected.agms)
            self.selected_at = time.monotonic()
            QtCore.QTimer.singleShot(4100, self.inspect_buttons)

        def inspect_buttons(self):
            if self.window is None:
                self.finish("no_window")
                return
            w = self.window
            result = {
                "agms_found": w.person_name.text().find("SURNAME") != -1,
                "start_enabled": w.start_btn.isEnabled(),
                "end_enabled": w.end_btn.isEnabled(),
                "position_status": w.active_status.text(),
                "selected_for_s": round(time.monotonic() - self.selected_at, 2),
                "central_present": w.store is not None,
                "pending": w.offline.pending_count(),
                "conflicts": len(w.offline.conflicts()),
            }
            print("BUTTON_RESULT:" + json.dumps(result, ensure_ascii=True), flush=True)
            os._exit(0)

        def finish(self, reason):
            print("BUTTON_TEST_ERROR:" + reason, flush=True)
            os._exit(2)

    QtWidgets.QApplication = InstrumentedApp
    MOD.run(["PositionTracking GUI test"])
    raise SystemExit("Unexpected Qt exit")


with tempfile.TemporaryDirectory() as d:
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    child = subprocess.run(
        [sys.executable, "-u", str(SCRIPT), "--qt-buttons-child", d],
        env=env, cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=24,
    )
    assert child.returncode == 0, (child.stdout, child.stderr[-1400:])
    matching = [x for x in child.stdout.splitlines() if x.startswith("BUTTON_RESULT:")]
    assert len(matching) == 1, (child.stdout, child.stderr[-1400:])
    result = json.loads(matching[0].partition(":")[2])
    assert result["agms_found"], result
    assert result["central_present"] and result["pending"] == 0 and result["conflicts"] == 0, result
    assert result["start_enabled"] and not result["end_enabled"], result
    assert "ΔΙΚΤΥΟ ΧΩΡΙΣ ΑΠΟΚΡΙΣΗ" in result["position_status"], result
    print("REPEATED_SYNC_MUST_NOT_DISABLE_START: PASS", json.dumps(result, ensure_ascii=True))

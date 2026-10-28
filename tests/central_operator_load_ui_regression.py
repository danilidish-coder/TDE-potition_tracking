"""Headless Qt checks: typing does not hammer the share; a hung read is recoverable."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtCore import QCoreApplication, QEvent
from shiboken6 import isValid
from PySide6.QtWidgets import QApplication
import position_tracking_ui_central as ui_central
from position_tracking_central import CentralOperator, UNCONFIRMED
from position_tracking_ui_central import CentralOperatorWindow
from central_operator_regression import write_personnel


class OperatorLoadUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-central-load-ui-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / ".tde_runtime"
        self.root.mkdir()
        write_personnel(self.root / "personnel.xlsx")
        self.services = SimpleNamespace(app_dir=lambda: self.directory)
        self.window = CentralOperatorWindow(self.services)
        self.addCleanup(self.destroy_window, self.window)
        self.window.show()
        self.wait(lambda: self.window._read_future is None and not self.window._dirty)

    def wait(self, predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate(), "Qt state did not settle: " + self.window.info.text())

    @staticmethod
    def destroy_window(window):
        if isValid(window):
            window.shutdown()
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def test_fast_typing_causes_one_lookup_after_the_pause(self):
        real = CentralOperator.lookup
        calls = []

        def counted(operator, agms):
            calls.append(agms)
            return real(operator, agms)

        with patch.object(CentralOperator, "lookup", counted):
            for text in ("9", "99", "999", "9990", "99900", "999001"):
                self.window.agms_input.setText(text)
                self.app.processEvents()
                time.sleep(0.02)
            # Nothing may be looked up while the operator is still typing.
            self.assertEqual(calls, [])
            self.wait(lambda: self.window.start_btn.isEnabled())
        self.assertEqual(calls, ["999001"])

    def test_hung_shared_read_is_abandoned_and_recheck_recovers(self):
        gate = threading.Event()
        self.addCleanup(gate.set)
        real = CentralOperator.lookup
        calls = []

        def hang_once(operator, agms):
            calls.append(agms)
            if len(calls) == 1:
                gate.wait(30)  # a stuck SMB call cannot be cancelled
            return real(operator, agms)

        with patch.object(ui_central, "READ_ABANDON_SECONDS", 0.4), \
                patch.object(CentralOperator, "lookup", hang_once):
            self.window.agms_input.setText("999001")
            self.wait(lambda: self.window._abandoned_reads == 1)
            self.assertIn(UNCONFIRMED, self.window.active_status.text())
            self.assertFalse(self.window.start_btn.isEnabled())
            self.assertTrue(self.window.recheck_btn.isEnabled(),
                            "operator must be able to retry without restarting")
            # The stuck call finishing later must not overwrite the new state.
            self.window.recheck_btn.click()
            self.wait(lambda: self.window.start_btn.isEnabled())
            self.assertNotEqual(self.window.person_name.text(), "—")
            gate.set()
            time.sleep(0.2)
            self.app.processEvents()
            self.assertTrue(self.window.start_btn.isEnabled())
        self.assertEqual(calls, ["999001", "999001"])

    def test_after_repeated_hangs_the_window_asks_for_a_restart(self):
        gate = threading.Event()
        self.addCleanup(gate.set)

        def always_hang(operator, agms):
            gate.wait(30)

        with patch.object(ui_central, "READ_ABANDON_SECONDS", 0.2), \
                patch.object(CentralOperator, "lookup", always_hang):
            self.window.agms_input.setText("999001")
            for _ in range(ui_central.MAX_ABANDONED_READS):
                self.wait(lambda: self.window._read_future is None and
                          not self.window._dirty or self.window._abandoned_reads >= ui_central.MAX_ABANDONED_READS)
                if self.window._abandoned_reads >= ui_central.MAX_ABANDONED_READS:
                    break
                self.window.recheck_btn.click()
            self.wait(lambda: self.window._abandoned_reads >= ui_central.MAX_ABANDONED_READS)
            self.assertFalse(self.window.recheck_btn.isEnabled())
            self.assertIn("Κλείστε και ανοίξτε ξανά", self.window.info.text())
            self.assertFalse(self.window.start_btn.isEnabled())
            self.assertFalse(self.window.end_btn.isEnabled())


if __name__ == "__main__":
    unittest.main()

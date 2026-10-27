"""Headless real Qt checks for bounded central-only operator interactions."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from position_tracking_central import PositionOutcome, UNCONFIRMED
from position_tracking_store import SharedEventStore
from position_tracking_ui_central import CentralOperatorWindow
from central_operator_regression import write_personnel


class OperatorUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-central-ui-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / ".tde_runtime"
        self.root.mkdir()
        write_personnel(self.root / "personnel.xlsx")
        def forbidden():
            raise AssertionError("Operator preview must never use a local profile or machine queue")
        self.services = SimpleNamespace(app_dir=lambda: self.directory,
                                         local_root=forbidden, machine_queue_root=forbidden)
        self.window = CentralOperatorWindow(self.services)
        self.addCleanup(self.window.close)
        self.window.show()
        self.wait(lambda: self.window._read_future is None and not self.window._dirty)

    def wait(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            QTest.qWait(5)
        self.assertTrue(predicate(), "Qt state did not settle")

    def select(self):
        self.window.agms_input.setText("999001")
        self.wait(lambda: self.window.start_btn.isEnabled())

    def start(self):
        self.select()
        self.window.start_btn.click()
        self.wait(lambda: self.window.end_btn.isEnabled())

    def test_real_central_start_end_from_buttons(self):
        self.start()
        self.assertIn("επιβεβαιώθηκε κεντρικά", self.window.info.text())
        self.window.end_btn.click()
        self.wait(lambda: self.window.start_btn.isEnabled())
        store = SharedEventStore(self.root)
        self.assertIsNone(store.get_active("999001"))
        self.assertEqual(len(store.search_personnel_sessions()), 1)
        self.assertFalse(hasattr(self.window, "offline"))
        self.assertFalse(hasattr(self.window, "offline_timer"))
        self.assertFalse(hasattr(self.window, "officer_card"))

    def test_exit_and_windows_account_change_preserve_central_active_position(self):
        self.start()
        start_id = self.window._active["event_id"]
        self.window.close()
        with patch.dict(os.environ, {"USERNAME": "another-synthetic-user"}):
            reopened = CentralOperatorWindow(self.services)
            self.addCleanup(reopened.close)
            reopened.agms_input.setText("999001")
            self.wait(lambda: reopened.end_btn.isEnabled())
        self.assertEqual(reopened._active["event_id"], start_id)
        self.assertEqual(len(SharedEventStore(self.root).iter_all_events()), 1)

    def test_blocked_read_keeps_qt_alive_and_coalesces_latest_selection(self):
        gate = threading.Event()
        entered = threading.Event()
        self.addCleanup(gate.set)
        original = self.window.endpoint.lookup
        calls = []
        def read(agms):
            calls.append(agms)
            entered.set()
            gate.wait(5)
            return original(agms)
        self.window.endpoint.lookup = read
        self.window.agms_input.setText("999001")
        self.wait(entered.is_set)
        self.window._read_started = time.monotonic() - 4
        for i in range(100):
            self.window.agms_input.setText(str(i))
        self.window.agms_input.setText("999002")
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(True))
        timer.start(10)
        QTest.qWait(150)
        timer.stop()
        self.assertGreaterEqual(len(ticks), 3)
        self.assertFalse(self.window.start_btn.isEnabled())
        self.assertFalse(self.window.end_btn.isEnabled())
        self.assertIn(UNCONFIRMED, self.window.active_status.text())
        self.assertEqual(calls, ["999001"])
        gate.set()
        self.wait(lambda: self.window.start_btn.isEnabled())
        self.assertEqual(self.window._person.agms, "999002")
        self.assertEqual(calls, ["999001", "999002"])

    def test_blocked_write_is_still_owned_after_ui_timeout(self):
        self.select()
        gate = threading.Event()
        entered = threading.Event()
        self.addCleanup(gate.set)
        original = self.window.endpoint.execute
        calls = []
        def write(request):
            calls.append(request.operation_id)
            entered.set()
            gate.wait(5)
            return original(request)
        self.window.endpoint.execute = write
        self.window.start_btn.click()
        self.wait(entered.is_set)
        self.window._action_started = time.monotonic() - 4
        QTest.qWait(150)
        self.assertIn(UNCONFIRMED, self.window.info.text())
        self.assertFalse(self.window.recheck_btn.isEnabled())
        self.assertTrue(self.window._action_future.running())
        for _ in range(100):
            self.window._act("START")
            self.window._recheck()
        self.assertEqual(len(calls), 1)
        gate.set()
        self.wait(lambda: self.window.end_btn.isEnabled())
        self.assertEqual(len(SharedEventStore(self.root).iter_all_events()), 1)

    def test_unknown_outcome_disables_mutations_until_explicit_check(self):
        self.select()
        checked = []
        self.window.endpoint.execute = lambda request: PositionOutcome("UNKNOWN", message=UNCONFIRMED)
        def check(request):
            checked.append(request.operation_id)
            return PositionOutcome("NOT_COMMITTED", message="Έγινε κεντρικός επανέλεγχος.")
        self.window.endpoint.check = check
        self.window.start_btn.click()
        self.wait(lambda: self.window._action_future is None)
        original_id = self.window._request.operation_id
        self.assertFalse(self.window.start_btn.isEnabled())
        self.assertFalse(self.window.end_btn.isEnabled())
        self.window.recheck_btn.click()
        self.wait(lambda: self.window.start_btn.isEnabled())
        self.assertEqual(checked, [original_id])
        self.assertEqual(SharedEventStore(self.root).iter_all_events(), [])

    def test_central_preview_launch_never_initializes_legacy_window_or_local_providers(self):
        source = Path(__file__).resolve().parents[1] / "src"
        program = """
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
import position_tracking_ui_application as ui
import position_tracking_ui_central as central
def forbidden(): raise AssertionError('local/legacy runtime called')
services = SimpleNamespace(app_dir=lambda: Path(sys.argv[2]), local_root=forbidden, machine_queue_root=forbidden)
real_window = central.CentralOperatorWindow
def construct(services):
    window = real_window(services)
    # launch has now created QApplication and its event dispatcher.
    QTimer.singleShot(250, QApplication.quit)
    return window
with patch.object(central, 'CentralOperatorWindow', side_effect=construct), patch.object(ui, 'MainWindow', side_effect=forbidden), patch('position_tracking_offline.OfflineJournal.__init__', side_effect=forbidden):
    raise SystemExit(ui.launch(['test', '--central-only'], services))
"""
        completed = subprocess.run([sys.executable, "-c", program, str(source), str(self.directory)],
                                   capture_output=True, text=True, timeout=10)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(list(self.directory.rglob("position_outbox.sqlite3")), [])


if __name__ == "__main__":
    unittest.main()

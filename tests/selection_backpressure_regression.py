"""Real Qt/executor: blocked remote reads must not queue every keystroke."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QLabel, QPushButton
from PySide6.QtTest import QTest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_ui_selection import PersonnelSelectionMixin
from position_tracking_offline import OfflineJournal
from position_tracking_personnel import PersonnelRecord

class SelectionBackpressure(unittest.TestCase):
    def test_blocked_selection_reads_are_coalesced_and_latest_selection_recovers(self):
        app = QApplication.instance() or QApplication([])
        release, entered = threading.Event(), threading.Event()
        calls = []
        class Store:
            def get_active(self, agms):
                calls.append(agms); entered.set()
                if not release.wait(8): raise RuntimeError('fixture deadline')
                return {'position': agms, 'direction': 'ΕΞΟΔΟΣ', 'timestamp': '2026-10-16T10:00:00'}
        class Window(PersonnelSelectionMixin, QWidget):
            pass
        with tempfile.TemporaryDirectory() as directory:
            w = Window(); w._state_pool = ThreadPoolExecutor(max_workers=2)
            w.store = Store(); w.offline = OfflineJournal(directory)
            w._position_operation_future = None
            w.agms_input = QLineEdit(w); w.person_name = QLabel(w); w.active_status = QLabel(w)
            w.start_btn = QPushButton(w); w.end_btn = QPushButton(w)
            w._people_by_agms = {str(i): PersonnelRecord(str(i), 'TEST', 'SYNTHETIC', 'ONLY') for i in (1, 2)}
            try:
                w.agms_input.setText('1'); w._agms_changed()
                deadline = time.monotonic() + 2
                while not entered.is_set() and time.monotonic() < deadline: QTest.qWait(10)
                self.assertTrue(entered.is_set())
                for i in range(200):
                    w.agms_input.setText(str(i % 2 + 1)); w._agms_changed()
                QTest.qWait(250)
                self.assertLessEqual(w._state_pool._work_queue.qsize(), 1,
                                     'Every selection was queued behind blocked SMB reads')
                self.assertLessEqual(len(calls), 1, 'At most one selection read may run')
                self.assertFalse(w.end_btn.isEnabled())
                release.set()
                end = time.monotonic() + 4
                while time.monotonic() < end and 'ΘΕΣΗ 2' not in w.active_status.text(): QTest.qWait(20)
                self.assertIn('ΘΕΣΗ 2', w.active_status.text())
                self.assertTrue(w.end_btn.isEnabled())
                self.assertLessEqual(len(calls), 2, 'Only initial and latest selections need reads')
            finally:
                release.set(); w._agms_query_serial += 1
                w._state_pool.shutdown(wait=True, cancel_futures=True)
                w.close(); app.processEvents()

if __name__ == '__main__': unittest.main()

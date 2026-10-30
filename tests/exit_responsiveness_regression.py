"""Confirmed exit must remain responsive, never acknowledge an unconfirmed END."""
import os
import faulthandler
faulthandler.enable()
faulthandler.dump_traceback_later(30, repeat=True)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QMessageBox
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_ui_lifecycle import WindowLifecycleMixin
from position_tracking_offline import OfflineJournal
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore

class ExitResponsiveness(unittest.TestCase):
    def exercise(self, failure=False, pending=False, remote=False, map_pending=False):
        app = QApplication.instance() or QApplication([])
        release = threading.Event(); entered = threading.Event(); calls = []; ack = []; ticks = []
        class Window(WindowLifecycleMixin, QWidget):
            def _agms_changed(self): pass
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); store = SharedEventStore(root / 'central')
            person = PersonnelRecord('1', 'TEST', 'SYNTHETIC', 'ONLY')
            started = store.start(person, '14', 'ΕΞΟΔΟΣ', client_id='OWN')
            active_all = store.active_all
            def read():
                calls.append(threading.get_ident()); entered.set()
                if not release.wait(5): raise RuntimeError('fixture deadline')
                if failure: raise OSError('injected central outage')
                return active_all()
            store.active_all = read
            def acknowledge(*args):
                self.assertIsNone(store.get_active('1'), 'ACK must follow confirmed END')
                ack.append(args)
            store.acknowledge_command = acknowledge
            w = Window(); w.store = store; w.client_id = 'OWN'; w._force_exit = False
            w.offline = OfflineJournal(root / 'queue'); w._offline_future = None; w._position_operation_future = None
            w.info = QLabel(w); w.start_btn = QPushButton(w); w.end_btn = QPushButton(w)
            for name in ('_network_pool', '_state_pool', '_position_pool'): setattr(w, name, ThreadPoolExecutor(max_workers=1))
            if pending: w.offline.enqueue('START', PersonnelRecord('2', 'TEST', 'SYNTHETIC', 'ONLY'), '1', 'ΕΙΣΟΔΟΣ')
            heartbeat = QTimer(w); heartbeat.timeout.connect(lambda: ticks.append(time.monotonic())); heartbeat.start(20)
            timer = threading.Timer(.8, release.set); timer.start()
            if map_pending:
                from concurrent.futures import Future
                w._map_mutation_future = Future()
                QTimer.singleShot(300, lambda:w._map_mutation_future.set_result("confirmed"))
            try:
                with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), patch.object(QMessageBox, 'critical') as errors, patch.object(QApplication, 'quit') as quit_app:
                    begin = time.monotonic()
                    if remote: w._start_confirmed_exit('original-command')
                    else: w._request_real_exit()
                    elapsed = time.monotonic() - begin
                    self.assertLess(elapsed, .25, 'Confirmed exit blocked the Qt thread on shared I/O')
                    if not pending:
                        deadline = time.monotonic() + 2
                        while not entered.is_set() and time.monotonic() < deadline:
                            app.processEvents()
                            time.sleep(.01)
                        self.assertTrue(entered.is_set())
                        if map_pending:self.assertTrue(w._map_mutation_future.done(), 'Exit overtook an in-flight map END')
                        w._start_confirmed_exit('duplicate-command')
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline and not quit_app.called and not errors.called:
                        app.processEvents()
                        time.sleep(.02)
                    if failure or pending:
                        self.assertFalse(quit_app.called); self.assertTrue(errors.called)
                        self.assertFalse(w._force_exit); self.assertEqual(ack, [])
                        self.assertEqual(store.get_active('1')['event_id'], started['event_id'])
                        self.assertEqual(w.offline.pending_count(), int(pending))
                    else:
                        self.assertTrue(quit_app.called); self.assertFalse(errors.called)
                        self.assertIsNone(store.get_active('1')); self.assertEqual(len(store.iter_all_events()), 2)
                        self.assertGreater(len(ticks), 10, 'Qt heartbeat stalled during shared I/O')
                        self.assertEqual(ack, [('original-command', 'OWN')] if remote else [])
                    self.assertTrue(all(t != threading.get_ident() for t in calls))
                    self.assertLessEqual(len(calls), 1, 'Duplicate exit must not submit another closure')
            finally:
                timer.cancel(); release.set(); heartbeat.stop()
                w._cleanup_client()
                for name in ('_network_pool', '_state_pool', '_position_pool'): getattr(w, name).shutdown(wait=True, cancel_futures=True)
                w.close(); app.processEvents()

    def test_normal_exit_closes_only_confirmed_own_start_off_gui(self): self.exercise()
    def test_failed_exit_preserves_active_start_and_does_not_acknowledge(self): self.exercise(failure=True)
    def test_pending_local_operation_prevents_false_success(self): self.exercise(pending=True)
    def test_remote_ack_follows_confirmed_end_off_gui(self): self.exercise(remote=True)
    def test_remote_failed_exit_is_not_acknowledged(self): self.exercise(failure=True, remote=True)
    def test_remote_exit_waits_for_inflight_map_mutation(self): self.exercise(remote=True,map_pending=True)

if __name__ == '__main__': unittest.main()

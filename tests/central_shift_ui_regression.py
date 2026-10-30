"""D1 real Qt: bounded officer I/O and shift close with open physical work."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QListWidget, QMessageBox, QPushButton, QWidget
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore
from position_tracking_ui_shifts import ShiftControllerMixin
from position_tracking_ui_shift_end import ShiftEndDialogMixin
from position_tracking_ui_admin import AdministrationMixin


class Window(AdministrationMixin, ShiftControllerMixin, ShiftEndDialogMixin, QWidget):
    def __init__(self, store, officer):
        super().__init__()
        self.store = store
        self.officer = officer
        self._people_by_agms = {}
        self._pending_prompt_active = False
        self.refreshes = 0
        self.config = SimpleNamespace(theme='light')

    def _live_map(self):
        pass

    def _officer_selected(self):
        return self.officer

    def _preview_list_dialog(self, title, intro, agms, allow_exclude):
        return True, agms, []

    def _refresh_shift_status(self):
        self.refreshes += 1


class ShiftUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-d1-qt-')
        self.addCleanup(self.temp.cleanup)
        self.store = SharedEventStore(self.temp.name)
        self.officer = PersonnelRecord('999099', 'TEST', 'OFFICER', 'SYNTHETIC')
        self.worker = PersonnelRecord('999001', 'TEST', 'WORKER', 'SYNTHETIC')
        self.event = self.store.start(self.worker, '1', 'ΕΙΣΟΔΟΣ', when=datetime.now() - timedelta(minutes=5))
        self.window = Window(self.store, self.officer)
        self.addCleanup(self.destroy)
        self.window.show()

    def destroy(self):
        worker = getattr(self.window, '_shift_action_worker', None)
        if worker:
            worker.close()
        self.window.close(); self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate(), 'D1 Qt/worker state did not settle')

    def test_start_shift_waits_off_gui_and_repeated_clicks_do_not_queue(self):
        entered = threading.Event()
        original = self.store.start_officer_shift
        calls = []
        def start(*args, **kwargs):
            calls.append(threading.get_ident()); entered.set()
            return original(*args, **kwargs)
        beats = []
        timer = QTimer(self.window); timer.timeout.connect(lambda: beats.append(1)); timer.start(10)
        with patch.object(self.store, 'start_officer_shift', start), \
                patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'critical') as errors:
            with self.store.officer_lock('__SHIFT_CONTROL__'):
                self.window._start_officer_shift_ui()
                self.wait(entered.is_set)
                self.window._start_officer_shift_ui()
                self.wait(lambda: len(beats) >= 3)
                self.assertTrue(self.window._shift_ui_pending)
                self.assertEqual(len(calls), 1)
                self.assertNotEqual(calls[0], threading.get_ident())
            self.wait(lambda: not self.window._shift_ui_pending)
            errors.assert_not_called()
        timer.stop()
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], self.event['event_id'])
        self.assertEqual(self.store.current_shift()['approved'], [self.worker.agms])

    def test_member_decision_waits_off_gui_and_preserves_physical_start(self):
        self.store.start_officer_shift(self.officer, initial_approved=[], initial_excluded=[self.worker.agms])
        other = PersonnelRecord('999002', 'TEST', 'NEXT', 'SYNTHETIC')
        event = self.store.start(other, '2', 'ΕΞΟΔΟΣ')
        entered, release = threading.Event(), threading.Event()
        calls = []
        original = self.store.set_shift_member_state
        def decision(*args):
            calls.append(threading.get_ident()); entered.set()
            if not release.wait(8):
                raise AssertionError('test did not release decision')
            return original(*args)
        with patch.object(self.store, 'set_shift_member_state', decision), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            try:
                self.window._resolve_pending_members()
                self.wait(entered.is_set)
                self.assertFalse(self.window._resolve_pending_members())
                self.assertEqual(len(calls), 1)
                self.assertNotEqual(calls[0], threading.get_ident())
                self.assertEqual(self.store.get_active(other.agms)['event_id'], event['event_id'])
            finally:
                release.set()
            self.wait(lambda: not self.window._shift_ui_pending)
        self.assertIn(other.agms, self.store.current_shift()['approved'])
        self.assertEqual(self.store.get_active(other.agms)['event_id'], event['event_id'])

    def complete_dialog(self, answer):
        clicked = []
        timer = QTimer(self.window)
        deadline = time.monotonic() + 5
        def interact():
            dlg = next((d for d in self.window.findChildren(QDialog) if d.isVisible()), None)
            if not dlg:
                return
            buttons = dlg.findChildren(QPushButton)
            button = next(b for b in buttons if b.text() == 'ΟΛΟΚΛΗΡΩΣΗ ΒΑΡΔΙΑΣ')
            if button.isEnabled() and not clicked:
                clicked.append(True); button.click()
                if answer == QMessageBox.No:
                    dlg.reject()
            elif time.monotonic() >= deadline:
                dlg.reject()
        timer.timeout.connect(interact); timer.start(10)
        try:
            with patch.object(QMessageBox, 'question', return_value=answer) as question, \
                    patch.object(QMessageBox, 'information'), patch.object(QMessageBox, 'critical') as errors:
                result = self.window._confirm_and_end_officer_shift(self.officer)
            self.assertTrue(clicked, 'Completion must be enabled with an open position')
            self.assertEqual(question.call_count, 1)
            self.assertIn('παραμένουν ενεργές', question.call_args.args[2])
            errors.assert_not_called()
            return result
        finally:
            timer.stop()

    def test_yes_completes_shift_with_open_position_and_no_actual_end(self):
        self.store.start_officer_shift(self.officer)
        self.assertTrue(self.complete_dialog(QMessageBox.Yes))
        self.assertIsNone(self.store.current_shift())
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], self.event['event_id'])
        self.assertEqual(len(self.store.iter_all_events()), 1)

    def test_no_leaves_shift_and_physical_position_unchanged(self):
        shift = self.store.start_officer_shift(self.officer)
        self.assertFalse(self.complete_dialog(QMessageBox.No))
        self.assertEqual(self.store.current_shift(), shift)
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], self.event['event_id'])
        self.assertEqual(len(self.store.iter_all_events()), 1)

    def test_existing_admin_membership_controls_keep_io_off_gui(self):
        self.store.start_officer_shift(self.officer)
        original = self.store.set_shift_member_state
        calls, steps = [], []
        entered, release = threading.Event(), threading.Event()
        def decision(*args):
            calls.append(threading.get_ident()); entered.set()
            if not release.wait(8):
                raise AssertionError('GUI did not remain responsive to release the worker')
            return original(*args)
        timer = QTimer(self.window)
        deadline = time.monotonic() + 5
        def interact():
            dlg = next((d for d in self.window.findChildren(QDialog)
                        if d.isVisible() and d.windowTitle() == 'ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ'), None)
            if not dlg:
                return
            listing = dlg.findChild(QListWidget)
            if listing.count() and not steps:
                steps.append('clicked'); listing.setCurrentRow(0)
                next(b for b in dlg.findChildren(QPushButton) if b.text() == 'ΕΞΑΙΡΕΣΗ').click()
            elif entered.is_set() and not release.is_set():
                steps.append('responsive'); release.set()
            elif release.is_set() and not self.window._shift_ui_pending:
                dlg.reject()
            elif time.monotonic() >= deadline:
                release.set(); dlg.reject()
        timer.timeout.connect(interact); timer.start(10)
        try:
            with patch.object(self.store, 'set_shift_member_state', decision), \
                    patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                    patch.object(QMessageBox, 'critical') as errors:
                self.window._admin()
            errors.assert_not_called()
        finally:
            release.set(); timer.stop()
        self.assertIn('responsive', steps)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(calls[0], threading.get_ident())
        self.assertIn(self.worker.agms, self.store.current_shift()['excluded'])
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], self.event['event_id'])


if __name__ == '__main__':
    unittest.main()

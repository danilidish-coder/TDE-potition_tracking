"""v1.2.8 officer window: chosen shift/remote times, corrections, station list, European dates."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDateTimeEdit, QDialog, QInputDialog, QMessageBox
from position_tracking_officer_store import OfficerStore
from position_tracking_ui_officer import CentralOfficerWindow
from position_tracking_ui_when import ask_moment, problem_with
from central_officer_regression import workbook


def minute(**delta):
    return (datetime.now() - timedelta(**delta)).replace(second=0, microsecond=0)


class ChosenTimes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-v128-qt-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name); self.root = self.directory / '.tde_runtime'; self.root.mkdir()
        (self.root / 'personnel.xlsx').write_bytes(workbook())
        self.services = SimpleNamespace(app_dir=lambda: self.directory, open_path=lambda path: None,
                                        local_root=None, machine_queue_root=None)
        self.window = CentralOfficerWindow(self.services)
        self.addCleanup(self.destroy, self.window)
        self.window.show(); self.window.officer.setText('999001'); self.window.refresh()
        self.wait(lambda: self.window._future is None and self.window._state is not None)

    def destroy(self, window):
        window.shutdown()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            window.close()
        window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def wait(self, predicate, seconds=6):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate(), self.window.info.text())

    def settle(self):
        self.wait(lambda: self.window._future is None and self.window._request is None and self.window._pending is None)

    @staticmethod
    def chosen(moment, reason='Synthetic reason for the change'):
        return dict(moment=moment, reason=reason, confirm_old=False)

    def run_with(self, moment, function, reason='Synthetic reason for the change'):
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen(moment, reason)), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as confirm:
            function(); self.settle()
        return confirm

    def test_shift_start_and_end_use_the_chosen_times(self):
        start = minute(hours=2)
        self.run_with(start, self.window.start_shift.click)
        shift = OfficerStore(self.root).current_shift()
        self.assertEqual(shift['start_at'], start.isoformat(timespec='seconds'))
        self.assertIn(start.strftime('%d/%m/%Y %H:%M'), self.window.shift_status.text())
        end = minute(minutes=30)
        confirm = self.run_with(end, self.window.end_shift.click)
        self.assertIn(end.strftime('%d/%m/%Y %H:%M'), confirm.call_args.args[2])
        self.assertEqual(OfficerStore(self.root).get_shift(shift['shift_id'])['end_at'], end.isoformat(timespec='seconds'))

    def test_remote_start_at_chosen_time_warns_about_overlap_and_station_label_is_listed(self):
        self.window.target.setText('999002')
        self.run_with(minute(hours=3), lambda: self.window.physical('REMOTE_START'))
        active = OfficerStore(self.root).get_active('999002')
        self.assertEqual(active['timestamp'], minute(hours=3).isoformat(timespec='seconds'))
        self.run_with(minute(hours=2), lambda: self.window.physical('REMOTE_END'))
        self.assertIsNone(OfficerStore(self.root).get_active('999002'))
        # Second work for the same person at a time that overlaps the first one: warning in the confirmation.
        confirm = self.run_with(minute(hours=2, minutes=30), lambda: self.window.physical('REMOTE_START'))
        text = confirm.call_args.args[2]
        self.assertIn('ΠΡΟΣΟΧΗ', text); self.assertIn('ίδιου ατόμου', text)
        # Future time is refused by the check before any confirmation or write.
        before = len(OfficerStore(self.root).officer_history())
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen(datetime.now() + timedelta(hours=2))), \
                patch.object(QMessageBox, 'warning') as warning, \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.physical('REMOTE_END'); self.settle()
        self.assertEqual(len(OfficerStore(self.root).officer_history()), before)

    def test_station_list_and_shift_time_correction(self):
        OfficerStore(self.root).write_client_heartbeat('station-a')
        self.window.refresh(); self.wait(lambda: self.window._future is None)
        self.assertIn('(ελεύθερος)', self.window.recipient.itemText(1))
        self.run_with(minute(hours=2), self.window.start_shift.click)
        original = OfficerStore(self.root).current_shift()
        new_start = minute(hours=3)
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen(new_start, 'Actual start was earlier')), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.shift_time_btn.click(); self.settle()
        corrected = OfficerStore(self.root).current_shift()
        self.assertEqual(corrected['start_at'], new_start.isoformat(timespec='seconds'))
        self.assertEqual(corrected['shift_id'], original['shift_id'])
        self.assertEqual(corrected['time_corrections'][0]['reason'], 'Actual start was earlier')

    def test_historical_add_accepts_a_typed_name_and_shows_the_person(self):
        self.run_with(minute(hours=3), self.window.start_shift.click)
        self.run_with(minute(minutes=10), self.window.end_shift.click)
        self.window.refresh(); self.wait(lambda: self.window._future is None and self.window.reports.count() > 1)
        shift_id = self.window.reports.itemData(1)
        self.window.reports.setCurrentIndex(1)
        seen = []
        def fake_exec(dialog):
            from PySide6.QtWidgets import QLineEdit, QLabel, QPlainTextEdit, QDialogButtonBox
            edit = dialog.findChildren(QLineEdit)[0]
            edit.setText('TARGET')
            seen.append([l.text() for l in dialog.findChildren(QLabel) if 'ΑΓΜΣ 999002' in l.text()])
            from position_tracking_ui_when import to_qt
            editors = dialog.findChildren(QDateTimeEdit)
            editors[0].setDateTime(to_qt(minute(hours=2))); editors[1].setDateTime(to_qt(minute(hours=1)))
            dialog.findChildren(QPlainTextEdit)[0].setPlainText('Work missed in the register')
            dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Ok).click()
            return QDialog.Accepted
        with patch.object(QDialog, 'exec', fake_exec), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.historical(); self.settle()
        self.assertTrue(seen and seen[0], 'dialog must show the matched person')
        self.assertEqual(len(OfficerStore(self.root).historical_for_shift(shift_id)), 1)
        self.assertEqual(OfficerStore(self.root).historical_for_shift(shift_id)[0]['agms'], '999002')
        # The chosen report stays selected after the refresh, and its text shows the added work.
        self.assertEqual(self.window.reports.currentData(), shift_id)
        from position_tracking_report_text import build_roster_shift_text
        store = OfficerStore(self.root)
        text = build_roster_shift_text(store, store.get_shift(shift_id), {p.agms: p for p in self.window._state['people']})
        self.assertIn('ΙΣΤΟΡΙΚΗ ΚΑΤΑΧΩΡΙΣΗ', text); self.assertIn('TARGET', text)

    def test_time_dialog_helper_rules(self):
        now = datetime(2026, 10, 29, 18, 0)
        self.assertEqual(problem_with(now + timedelta(hours=1), now)[0], 'Δεν επιτρέπεται μελλοντική ώρα.')
        self.assertTrue(problem_with(now - timedelta(hours=25), now)[1])
        self.assertEqual(problem_with(now - timedelta(hours=1), now), ('', ''))
        self.assertTrue(problem_with(now - timedelta(hours=1), now, minimum=now, minimum_text='νωρίς')[0])
        default = minute(minutes=5)
        with patch.object(QDialog, 'exec', return_value=QDialog.Accepted):
            answer = ask_moment(None, 'T', 'P', default)
        self.assertEqual(answer['moment'], default)
        with patch.object(QDialog, 'exec', return_value=QDialog.Rejected):
            self.assertIsNone(ask_moment(None, 'T', 'P', default))


if __name__ == '__main__':
    unittest.main()

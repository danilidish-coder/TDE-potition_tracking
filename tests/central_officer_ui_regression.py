"""Real Qt D2 confirmation, unknown state, worker ownership and central output."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import subprocess
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox
from position_tracking_central import CentralOperator
from position_tracking_officer_store import OfficerStore
from position_tracking_ui_officer import CentralOfficerWindow
from position_tracking_ui_central import CentralOperatorWindow
from central_officer_regression import workbook


class OfficerUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-officer-qt-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name); self.root = self.directory / '.tde_runtime'; self.root.mkdir()
        (self.root / 'personnel.xlsx').write_bytes(workbook())
        self.opened = []
        def forbidden():
            raise AssertionError('No local business profile/queue permitted')
        self.services = SimpleNamespace(app_dir=lambda:self.directory, open_path=self.opened.append,
                                         local_root=forbidden, machine_queue_root=forbidden)
        self.window = CentralOfficerWindow(self.services)
        self.addCleanup(self.destroy, self.window)
        self.window.show(); self.window.officer.setText('999001'); self.window.refresh()
        self.wait(lambda:self.window._future is None and self.window._state is not None)

    def destroy(self, window):
        window.shutdown()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            window.close()
        window.deleteLater(); QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents(); time.sleep(.005)
        self.assertTrue(predicate(), 'D2 Qt state did not settle: ' + self.window.info.text())

    def settle(self):
        self.wait(lambda:self.window._future is None and self.window._request is None)

    @staticmethod
    def chosen(moment=None, reason='Explicit synthetic officer reason'):
        return dict(moment=moment or datetime.now().replace(second=0, microsecond=0), reason=reason, confirm_old=False)

    def physical(self, action):
        self.window.target.setText('999002')
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen()), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.physical(action)
            self.settle()

    def test_no_confirmation_leaves_shift_positions_and_audit_unchanged(self):
        before = OfficerStore(self.root).officer_history()
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen()), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            self.window.start_shift.click()
        self.assertIsNone(OfficerStore(self.root).current_shift())
        self.assertEqual(OfficerStore(self.root).officer_history(), before)
        self.assertIsNone(self.window._request)

    def test_remote_start_correction_and_end_keep_complete_declared_history(self):
        self.physical('REMOTE_START')
        before = OfficerStore(self.root).get_active('999002')
        new_moment = (datetime.fromisoformat(before['timestamp']) - timedelta(minutes=1)).replace(second=0, microsecond=0)
        new_time = new_moment.isoformat(timespec='seconds')
        with patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen(new_moment, 'Correct actual start')) as prompts, \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as confirm:
            self.window.physical('CORRECT_START')
            self.settle()
        self.assertEqual(prompts.call_count, 1)  # One dialog: actual time and reason; never a second officer AGMS.
        self.assertIn('TARGET', confirm.call_args.args[2])
        self.physical('REMOTE_END')
        store = OfficerStore(self.root)
        self.assertIsNone(store.get_active('999002'))
        history = store.officer_history()
        self.assertEqual(len(history), 3)
        self.assertTrue(all(a['declared_officer']['agms'] == '999001' for a in history))
        self.assertEqual(history[1]['record_id'], before['event_id'])
        self.assertEqual(history[1]['before']['timestamp'], before['timestamp'])
        self.assertEqual(history[1]['after']['timestamp'], new_time)
        self.assertEqual(store.search_personnel_sessions()[0]['start_at'], new_time)

    def test_blocked_worker_keeps_gui_responsive_and_has_no_second_job(self):
        entered, release = threading.Event(), threading.Event(); calls = []
        execute = self.window.endpoint.execute
        def slow(request):
            calls.append(request.action_id); entered.set()
            if not release.wait(8): raise AssertionError('Test did not release the worker')
            return execute(request)
        beats = []; timer = QTimer(self.window); timer.timeout.connect(lambda:beats.append(1)); timer.start(10)
        with patch.object(self.window.endpoint, 'execute', slow), \
                patch('position_tracking_ui_officer.ask_moment', side_effect=lambda *a, **k: self.chosen()), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            try:
                self.window.start_shift.click(); self.wait(entered.is_set)
                self.window.change('SHIFT_START'); self.wait(lambda:len(beats)>=3)
                self.assertEqual(len(calls), 1)
                self.assertFalse(self.window.officer.isEnabled())
            finally:
                release.set(); timer.stop()
            self.settle()
        self.assertEqual(len(OfficerStore(self.root).officer_history()), 1)

    def test_unknown_ack_retains_same_request_until_explicit_recheck(self):
        original = OfficerStore._commit_position_attempt; dropped = []
        def lose(store, *args):
            result = original(store, *args)
            if not dropped:
                dropped.append(True); raise OSError('synthetic ACK lost')
            return result
        self.window.target.setText('999002')
        with patch.object(OfficerStore, '_commit_position_attempt', lose), \
                patch.object(self.window.endpoint, 'check', side_effect=OSError('synthetic readback outage')), \
                patch('position_tracking_ui_officer.ask_moment', return_value=self.chosen(reason='Explicit synthetic reason')), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.physical('REMOTE_START')
            self.wait(lambda:self.window._future is None)
        request = self.window._request
        self.assertIsNotNone(request)
        self.assertFalse(self.window.remote_start.isEnabled())
        self.window.refresh_btn.click(); self.settle()
        self.assertEqual(OfficerStore(self.root).get_active('999002')['event_id'], request.action_id)
        self.assertEqual(len(OfficerStore(self.root).officer_history()), 1)

    def test_central_import_preview_confirmation_and_other_station_visibility(self):
        path = self.directory / 'synthetic-update.xlsx'; path.write_bytes(workbook('UPDATED'))
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path),'')), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            self.window.import_btn.click(); self.settle()
        self.assertEqual(CentralOperator(self.root,self.root/'personnel.xlsx').lookup('999002')[0].surname, 'TARGET')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path),'')), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.import_btn.click(); self.settle()
        self.assertEqual(CentralOperator(self.root,self.root/'personnel.xlsx').lookup('999002')[0].surname, 'UPDATED')
        self.assertEqual(self.window.officer.text(), '999001')
        self.assertEqual(len(OfficerStore(self.root).officer_history()), 1)

    def test_shift_close_with_active_position_and_existing_pdf_engine(self):
        self.physical('REMOTE_START')
        with patch('position_tracking_ui_officer.ask_moment', side_effect=lambda *a, **k: self.chosen()), \
                patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.start_shift.click(); self.settle()
            self.window.end_shift.click(); self.settle()
        self.assertIsNotNone(OfficerStore(self.root).get_active('999002'))
        self.window.report_btn.click(); self.settle()
        self.assertTrue(self.opened, self.window.info.text())
        self.assertTrue(self.opened[0].read_bytes().startswith(b'%PDF'))
        self.assertTrue(self.opened[0].is_relative_to(self.root))

    def test_existing_statistics_pin_is_still_required(self):
        with patch.object(QInputDialog, 'getText', return_value=('WRONG',True)), \
                patch.object(QMessageBox, 'warning') as warning:
            self.window.stats_btn.click()
        self.assertEqual(warning.call_count, 1)
        self.assertEqual(self.opened, [])

    def test_official_message_reaches_simple_operator_and_can_be_acknowledged(self):
        operator = CentralOperatorWindow(self.services); self.addCleanup(self.destroy, operator)
        operator.show(); self.wait(lambda:operator.endpoint is not None and operator._read_future is None)
        operator._poll_mail(); self.wait(lambda:operator._mail_future is None)
        self.window.refresh(); self.settle()
        self.window.message.setPlainText('SYNTHETIC OFFICIAL MESSAGE')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.message_btn.click()
        self.settle(); operator._poll_mail(); self.wait(lambda:operator._mail_future is None)
        self.assertEqual(operator.service_message.text(), 'SYNTHETIC OFFICIAL MESSAGE')
        self.assertFalse(hasattr(operator, 'start_shift'))
        operator.ack_message.click(); self.wait(lambda:operator._mail_future is None)
        self.assertEqual(operator.service_message.text(), '')
        self.assertEqual(OfficerStore(self.root).pending_messages(operator._client_id), [])

    def test_officer_entry_flag_exits_normally_without_legacy_profile_or_queue(self):
        program = '''
import sys
from types import SimpleNamespace
sys.path.insert(0,sys.argv[1])
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from position_tracking_ui_officer import CentralOfficerWindow
import position_tracking_ui_application as app
def forbidden(*args): raise AssertionError('legacy/offline path called')
app.MainWindow=forbidden
original=CentralOfficerWindow.show
def show(window):
    original(window)
    QTimer.singleShot(200,QApplication.instance().quit)
CentralOfficerWindow.show=show
services=SimpleNamespace(app_dir=lambda:sys.argv[2],open_path=forbidden,local_root=forbidden,machine_queue_root=forbidden)
raise SystemExit(app.launch(['tde','--central-officer'],services))
'''
        result = subprocess.run([sys.executable,'-c',program,str(Path(__file__).resolve().parents[1]/'src'),
                                 str(self.directory)],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)


    def test_historical_action_requires_selected_report(self):
        self.assertIsNone(self.window.reports.currentData() or None)
        with patch.object(QMessageBox,'warning') as warning:
            self.window.historical_btn.click()
        self.assertEqual(warning.call_count,1)
        self.assertEqual(OfficerStore(self.root).officer_history(),[])


if __name__ == '__main__':
    unittest.main()

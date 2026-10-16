"""Real application event loop/process exit offline; never infer safety from roster."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_offline import OfflineJournal
from position_tracking_personnel import PersonnelRecord
from position_tracking_settings import AppConfig


def child(case, root):
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    import position_tracking_ui_application as application
    root = Path(root); settings = root / 'settings.json'; central = root / 'absent-central'
    class Config(AppConfig):
        @classmethod
        def load(cls): return super().load(path=settings, app_directory=root)
        def save(self): return super().save(path=settings)
    Config(central_root=str(central), shared_exe_path=str(root/'absent.exe')).save()
    journal = OfflineJournal(root/'queue'); person = PersonnelRecord('1','TEST','SYNTHETIC','ONLY')
    if case in ('pending', 'conflict', 'applied-unclosed'):
        op = journal.enqueue('START', person, '14', 'ΕΞΟΔΟΣ')
        if case!='pending': journal._mark(op['operation_id'], 'CONFLICT' if case=='conflict' else 'APPLIED', 'fixture')
    elif case=='observed-active':
        journal.remember('1', {'event_id':'known-start','agms':'1','position':'14'})
    elif case=='applied-closed':
        from position_tracking_store import SharedEventStore
        store=SharedEventStore(central)
        journal.enqueue('START',person,'14','ΕΞΟΔΟΣ'); journal.sync(store,PersonnelRecord)
        journal.enqueue('END',person); journal.sync(store,PersonnelRecord)
        central.rename(root/'completed-central-retained')
    elif case=='corrupt-observed':
        with journal._db() as db: db.execute('INSERT INTO observed VALUES(?,?,?)', ('1','{broken','fixture'))
    def snapshot():
        with journal._db() as db:
            return {'operations':db.execute('SELECT * FROM operations ORDER BY rowid').fetchall(),
                    'observed':db.execute('SELECT * FROM observed ORDER BY agms').fetchall()}
    before = snapshot(); windows=[]; errors=[]; confirmations=[]; deadline_fired=[]
    real_window = application.MainWindow
    def construct(services):
        w = real_window(services); windows.append(w)
        if case=='background-inflight':
            from concurrent.futures import Future
            w._agms_future=Future()
        if case=='position-attempted': w._position_activity_attempted=True
        def drive_dialogs():
            for box in QApplication.topLevelWidgets():
                if not isinstance(box, QMessageBox) or not box.isVisible(): continue
                if box.standardButtons() & QMessageBox.Yes:
                    confirmations.append(box.text()); QTest.mouseClick(box.button(QMessageBox.Yes), Qt.LeftButton)
                else:
                    errors.append(box.text()); QTest.mouseClick(box.button(QMessageBox.Ok), Qt.LeftButton)
                    QTimer.singleShot(50, lambda:QApplication.exit(7 if case in ('empty','applied-closed') else 0))
        timer = QTimer(w); timer.timeout.connect(drive_dialogs); timer.start(20)
        w._test_dialog_timer=timer
        def deadline(): deadline_fired.append(True); QApplication.exit(9)
        QTimer.singleShot(4000, deadline)
        if case=='remote-idle': QTimer.singleShot(100,lambda:w._start_confirmed_exit('unacknowledged-command'))
        else: QTimer.singleShot(100, w.exit_app_btn.click)
        return w
    from position_tracking_ui_context import WindowServices
    services=WindowServices(Config,lambda:root,lambda:root/'local',lambda:root/'queue',lambda p:None)
    with patch.object(application,'MainWindow',side_effect=construct): code=application.launch([],services)
    w=windows[0]
    result={'case':case,'code':code,'confirmed':bool(confirmations),'errors':errors,
            'force_exit':w._force_exit,'people':len(w.people),'central_created':central.exists(),
            'unchanged_journal':snapshot()==before,'deadline_fired':bool(deadline_fired),'exit_mode':getattr(w,'_exit_mode',None)}
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return code


class IdleExitRegression(unittest.TestCase):
    def exercise(self, case, allowed):
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',case,directory],
                cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=12,
                env=dict(os.environ,PYTHONUTF8='1',PYTHONIOENCODING='utf-8'))
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(report['confirmed'],case!='remote-idle'); self.assertFalse(report['central_created'])
            self.assertEqual(report['people'],0); self.assertTrue(report['unchanged_journal'])
            self.assertFalse(report['deadline_fired'])
            self.assertEqual(report['force_exit'],allowed)
            self.assertEqual(bool(report['errors']),not allowed)
            if allowed:self.assertEqual(report['exit_mode'],'local_idle')

    def test_confirmed_closed_history_allows_idle_application_exit(self): self.exercise('applied-closed',True)
    def test_remote_command_cannot_skip_central_ack(self): self.exercise('remote-idle',False)
    def test_inflight_cache_read_prevents_local_shortcut(self): self.exercise('background-inflight',False)
    def test_attempted_position_action_prevents_local_shortcut(self): self.exercise('position-attempted',False)
    def test_real_startup_and_process_exit_without_central_roster_or_operations(self): self.exercise('empty',True)
    def test_pending_start_is_not_waived_by_empty_roster(self): self.exercise('pending',False)
    def test_conflict_is_not_waived_by_empty_roster(self): self.exercise('conflict',False)
    def test_applied_unclosed_start_blocks_even_if_observed_cache_is_empty(self): self.exercise('applied-unclosed',False)
    def test_known_active_position_blocks_without_pending_operations(self): self.exercise('observed-active',False)
    def test_corrupt_observation_is_not_interpreted_as_empty(self): self.exercise('corrupt-observed',False)

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--child': raise SystemExit(child(sys.argv[2],sys.argv[3]))
    unittest.main()

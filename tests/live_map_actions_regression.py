"""Real Qt map: blocked shared reads stay off GUI; END guards selected START."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys,tempfile,threading,time,unittest,json
from unittest.mock import patch
from PySide6.QtCore import QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QInputDialog
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from position_tracking_ui_map import LiveMapDialog
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord

class LiveMapActions(unittest.TestCase):
    def wait(self,predicate,seconds=5):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return
            QTest.qWait(10)
        self.fail('map operation did not complete')

    def fixture(self,directory):
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        store=SharedEventStore(Path(directory)/'central')
        person=PersonnelRecord('1','TEST','SYNTHETIC','ONLY');officer=PersonnelRecord('9','TEST','OFFICER','ONLY')
        started=store.start(person,'14','ΕΞΟΔΟΣ',client_id='old-owner')
        dialog=LiveMapDialog(store,{'1':person},lambda:officer)
        dialog.timer.stop();dialog._live_future.result(timeout=2)
        dialog.active_person.addItem('SYNTHETIC','1');dialog.show();QTest.qWait(30)
        return app,store,person,started,dialog

    def cleanup(self,app,dialog):
        dialog.timer.stop();dialog.close();dialog._live_pool.shutdown(wait=True,cancel_futures=True)
        dialog.deleteLater();app.processEvents()

    def test_delayed_selected_read_does_not_block_qt(self):
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            release=threading.Event();entered=threading.Event();ticks=[]
            original=store.get_active
            def delayed(agms):
                entered.set()
                if not release.wait(4):raise RuntimeError('fixture deadline')
                return original(agms)
            heartbeat=QTimer(dialog);heartbeat.timeout.connect(lambda:ticks.append(time.monotonic()));heartbeat.start(20)
            timer=threading.Timer(.8,release.set);timer.start()
            try:
                with patch.object(store,'get_active',side_effect=delayed),patch.object(QMessageBox,'question',return_value=QMessageBox.No) as question:
                    begin=time.monotonic();QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton)
                    self.assertLess(time.monotonic()-begin,.25,'Map selected read blocked Qt on shared I/O')
                    self.wait(lambda:question.called)
                    self.assertGreater(len(ticks),10)
                self.assertEqual(store.get_active('1')['event_id'],started['event_id'])
                self.assertEqual(len(store.iter_all_events()),1)
            finally:
                release.set();timer.cancel();heartbeat.stop();self.cleanup(app,dialog)

    def test_end_cannot_close_replacement_start_after_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory);replacement=[]
            def confirm(*args):
                store.end(person,expected_start_event_id=started['event_id'])
                replacement.append(store.start(person,'14','ΕΞΟΔΟΣ',client_id='replacement-owner'))
                return QMessageBox.Yes
            try:
                with patch.object(QMessageBox,'question',side_effect=confirm),patch.object(QMessageBox,'critical') as errors,patch.object(QMessageBox,'information') as info:
                    QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton)
                    self.wait(lambda:errors.called or info.called)
                    active=store.get_active('1')
                    self.assertIsNotNone(active,'Stale map END closed the replacement START')
                    self.assertEqual(active['event_id'],replacement[0]['event_id'])
                    self.assertTrue(errors.called);self.assertFalse(info.called)
                    self.assertEqual(len(store.iter_all_events()),3,'No additional END may be written')
            finally:self.cleanup(app,dialog)

    def test_closing_map_during_read_cannot_later_issue_end(self):
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            entered=threading.Event();release=threading.Event();original=store.get_active
            def delayed(agms):
                entered.set()
                if not release.wait(4):raise RuntimeError('fixture deadline')
                return original(agms)
            try:
                with patch.object(store,'get_active',side_effect=delayed),patch.object(QMessageBox,'question') as question:
                    QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton)
                    self.wait(entered.is_set);future=dialog._map_operation_future
                    dialog.reject();self.assertFalse(dialog.isVisible())
                    release.set();self.wait(future.done);QTest.qWait(150)
                    self.assertFalse(question.called,'A closed dialog must not continue into END confirmation')
                self.assertEqual(store.get_active('1')['event_id'],started['event_id'])
                self.assertEqual(len(store.iter_all_events()),1)
            finally:release.set();self.cleanup(app,dialog)

    def test_pending_end_keeps_map_open_and_cannot_be_duplicated(self):
        from PySide6.QtWidgets import QWidget
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            entered=threading.Event();release=threading.Event();original=store.end;calls=[]
            def delayed(*args,**kwargs):
                calls.append(kwargs);entered.set()
                if not release.wait(4):raise RuntimeError('fixture deadline')
                return original(*args,**kwargs)
            owner=QWidget();dialog.setParent(owner,dialog.windowFlags());dialog.show()
            try:
                with patch.object(store,'end',side_effect=delayed),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'information') as info,patch.object(QMessageBox,'critical') as errors:
                    QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton);self.wait(entered.is_set)
                    self.assertIs(owner._map_mutation_future,dialog._map_operation_future)
                    self.assertTrue(owner._position_activity_attempted)
                    dialog.reject();self.assertTrue(dialog.isVisible())
                    self.assertFalse(info.called);self.assertFalse(dialog.end_active_btn.isEnabled())
                    QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton)
                    release.set()
                    self.wait(lambda: info.called or errors.called, seconds=12)
                    self.assertFalse(errors.called, 'Map END returned error: ' + str(errors.call_args))
                    self.assertTrue(info.called, 'Confirmed END missing GUI acknowledgment')
                    self.assertEqual(len(calls),1)
                    self.assertEqual(calls[0]['expected_start_event_id'],started['event_id'])
                    dialog.reject();self.assertFalse(dialog.isVisible())
                self.assertIsNone(store.get_active('1'));self.assertEqual(len(store.iter_all_events()),2)
            finally:release.set();self.cleanup(app,dialog);owner.close()

    def test_missing_selected_start_identity_cannot_issue_end(self):
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            uncertain=dict(started,event_id='')
            try:
                with patch.object(store,'get_active',return_value=uncertain),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'critical') as errors,patch.object(store,'end',wraps=store.end) as end:
                    QTest.mouseClick(dialog.end_active_btn,Qt.LeftButton);self.wait(lambda:errors.called)
                    self.assertFalse(end.called)
                self.assertEqual(store.get_active('1')['event_id'],started['event_id'])
                self.assertEqual(len(store.iter_all_events()),1)
            finally:self.cleanup(app,dialog)

    def test_correction_read_does_not_block_qt(self):
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            release=threading.Event();ticks=[];original=store.get_active
            def delayed(agms):
                if not release.wait(4):raise RuntimeError('fixture deadline')
                return original(agms)
            heartbeat=QTimer(dialog);heartbeat.timeout.connect(lambda:ticks.append(time.monotonic()));heartbeat.start(20)
            timer=threading.Timer(.8,release.set);timer.start()
            try:
                with patch.object(store,'get_active',side_effect=delayed),patch.object(QInputDialog,'getText',return_value=('',False)) as prompt:
                    begin=time.monotonic();QTest.mouseClick(dialog.edit_start_btn,Qt.LeftButton)
                    self.assertLess(time.monotonic()-begin,.25,'Correction read blocked Qt on shared I/O')
                    self.wait(lambda:prompt.called);self.assertGreater(len(ticks),10)
                self.assertFalse(list(store.corrections.glob('*.json')))
            finally:release.set();timer.cancel();heartbeat.stop();self.cleanup(app,dialog)

    def test_correction_cannot_modify_replacement_start_after_confirmation(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory);replacement=[]
            revised=datetime.fromisoformat(started['timestamp']).replace(hour=0,minute=0,second=0)
            def confirm(*args):
                store.end(person,expected_start_event_id=started['event_id'])
                replacement.append(store.start(person,'14','ΕΞΟΔΟΣ',client_id='replacement-owner'))
                return QMessageBox.Yes
            try:
                with patch.object(QInputDialog,'getText',side_effect=[(revised.strftime('%d/%m/%Y %H:%M'),True),('SYNTHETIC REASON',True)]),patch.object(QMessageBox,'question',side_effect=confirm),patch.object(QMessageBox,'critical') as errors,patch.object(QMessageBox,'information') as info:
                    QTest.mouseClick(dialog.edit_start_btn,Qt.LeftButton)
                    self.wait(lambda:errors.called or info.called)
                    self.assertTrue(errors.called);self.assertFalse(info.called)
                    active=store.get_active('1')
                    self.assertEqual(active['event_id'],replacement[0]['event_id'])
                    self.assertEqual(active['timestamp'],replacement[0]['timestamp'])
                    self.assertFalse(list(store.corrections.glob('*.json')),'Stale correction changed a replacement START')
                    self.assertEqual(len(store.iter_all_events()),3)
            finally:self.cleanup(app,dialog)

    def test_confirmed_correction_preserves_raw_start_and_identity(self):
        from datetime import datetime
        with tempfile.TemporaryDirectory() as directory:
            app,store,person,started,dialog=self.fixture(directory)
            revised=datetime.fromisoformat(started['timestamp']).replace(hour=0,minute=0,second=0)
            try:
                with patch.object(QInputDialog,'getText',side_effect=[(revised.strftime('%d/%m/%Y %H:%M'),True),('SYNTHETIC REASON',True)]),patch.object(QMessageBox,'question',return_value=QMessageBox.Yes),patch.object(QMessageBox,'critical') as errors,patch.object(QMessageBox,'information') as info:
                    QTest.mouseClick(dialog.edit_start_btn,Qt.LeftButton);self.wait(lambda:info.called or errors.called)
                    self.assertFalse(errors.called);self.assertTrue(info.called)
                    active=store.get_active('1')
                    self.assertEqual(active['event_id'],started['event_id'])
                    self.assertEqual(active['timestamp'],revised.isoformat(timespec='seconds'))
                    raw=[json.loads(p.read_text(encoding='utf-8')) for p in store.events.rglob('*.json')]
                    self.assertEqual(len(raw),1);self.assertEqual(raw[0]['timestamp'],started['timestamp'])
                    self.assertEqual(len(list(store.corrections.glob('*.json'))),1)
            finally:self.cleanup(app,dialog)

if __name__=='__main__':unittest.main()

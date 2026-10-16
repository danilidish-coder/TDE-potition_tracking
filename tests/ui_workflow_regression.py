"""Actual Qt input: offline START/END, restart replay, online actions and dialogs."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from openpyxl import Workbook
from PySide6.QtCore import Qt,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox,QInputDialog
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from position_tracking_settings import AppConfig
from position_tracking_ui_context import WindowServices
from position_tracking_ui_main import MainWindow

class ActualUIWorkflow(unittest.TestCase):
    def test_offline_restart_and_online_receipts_preserve_ids_and_timestamps(self):
        app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
        windows=[];notices=[]
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);settings=base/'local'/'settings.json';central=base/'central';roster=base/'people.xlsx'
            wb=Workbook();ws=wb.active;ws.append(['ΑΓΜΣ','ΒΑΘΜΟΣ','ΕΠΩΝΥΜΟ','ΟΝΟΜΑ']);ws.append(['910001','ΑΣΤ','ΔΟΚΙΜΗ','ΠΡΟΣΩΠΙΚΟ']);wb.save(roster)
            class Config(AppConfig):
                @classmethod
                def load(cls):return super().load(path=settings,app_directory=base)
                def save(self):return super().save(path=settings)
            Config(central_root=str(central),personnel_file=str(roster)).save()
            services=WindowServices(Config,lambda:base,lambda:base/'local',lambda:base/'queue',lambda p:None)
            def wait(predicate):
                end=time.monotonic()+12
                while time.monotonic()<end:
                    if predicate():return
                    QTest.qWait(10)
                self.fail('Qt workflow condition did not complete')
            def open_window():
                w=MainWindow(services);windows.append(w);w.show()
                wait(lambda:w.windowHandle().isExposed())
                QTest.keyClicks(w.agms_input,'910001');wait(lambda:w.start_btn.isEnabled())
                return w
            def close_window(w):
                for timer in (w.shift_timer,w.communication_timer,w.offline_timer):timer.stop()
                w._cleanup_client()
                for pool in (w._network_pool,w._position_pool,w._state_pool):pool.shutdown(wait=True,cancel_futures=True)
                w._force_exit=True;w.close();app.processEvents()
            with patch.object(QMessageBox,'warning',side_effect=lambda *a:notices.append(a[1:]) or QMessageBox.Ok),patch.object(QMessageBox,'critical',side_effect=AssertionError('Unexpected UI error')):
                try:
                    w=open_window();w.position.setCurrentText('14')
                    self.assertEqual(w.direction.currentText(),'ΕΞΟΔΟΣ')
                    QTest.mouseClick(w.start_btn,Qt.LeftButton)
                    wait(lambda:w.offline.pending_count()==1 and w._position_operation_future is None and w.end_btn.isEnabled())
                    QTest.mouseClick(w.end_btn,Qt.LeftButton)
                    wait(lambda:w.offline.pending_count()==2 and w._position_operation_future is None)
                    original=w.offline._rows(('PENDING',));self.assertEqual([x['kind'] for x in original],['START','END'])
                    self.assertFalse(central.exists());close_window(w)
                    central.mkdir();w=open_window()
                    wait(lambda:w.store is not None and w.offline.pending_count()==0)
                    events={e['event_id']:e for e in w.store.iter_all_events()}
                    self.assertEqual(set(events),{x['id'] for x in original})
                    for row in original:self.assertEqual(events[row['id']]['timestamp'],row['created_at'])
                    self.assertEqual(events[original[1]['id']]['start_event_id'],original[0]['id'])
                    self.assertEqual(events[original[0]['id']]['position'],'14')
                    self.assertEqual(events[original[0]['id']]['direction'],'ΕΞΟΔΟΣ')
                    w.position.setCurrentText('1');wait(lambda:w.start_btn.isEnabled())
                    QTest.mouseClick(w.start_btn,Qt.LeftButton)
                    wait(lambda:w.offline.pending_count()==0 and w.store.get_active('910001') is not None and w._position_operation_future is None and w.end_btn.isEnabled())
                    self.assertEqual(w.store.get_active('910001')['direction'],'ΕΙΣΟΔΟΣ')
                    QTest.mouseClick(w.end_btn,Qt.LeftButton)
                    wait(lambda:w.offline.pending_count()==0 and w.store.get_active('910001') is None and w._position_operation_future is None)
                    self.assertEqual(len(list(w.store.iter_all_events())),4)
                    self.assertEqual(len(w.store.completed_sessions_all()),2)
                    rows=w.offline._rows(('APPLIED',));self.assertEqual(len(rows),4)
                    final={e['event_id']:e for e in w.store.iter_all_events()}
                    for row in rows:self.assertEqual(final[row['id']]['timestamp'],row['created_at'])
                    titles=[]
                    def close_modal():
                        dialog=app.activeModalWidget()
                        if dialog is not None:titles.append(dialog.windowTitle());dialog.close()
                    for button in (w.archive_btn,w.active_positions_btn):
                        QTimer.singleShot(30,close_modal);button.click()
                    self.assertEqual(len(titles),2)
                    with patch.object(QInputDialog,'getText',return_value=('wrong-test-pin',True)):
                        w.history_btn.click()
                    self.assertTrue(any('Λανθασμένος' in str(n) for n in notices))
                finally:
                    for w in windows:close_window(w)

if __name__=='__main__':unittest.main()

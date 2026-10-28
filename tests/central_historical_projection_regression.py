"""D3-B projection checks on isolated synthetic data."""
from datetime import timedelta
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from central_historical_work_stage_a import HistoricalWorkStageA
from position_tracking_report_text import build_roster_shift_text
from position_tracking_store import SharedEventStore

class HistoryReportProjection(HistoricalWorkStageA):
    def test_late_person_appears_in_report_and_history(self):
        self.add()
        shift=self.store.get_shift(self.shift_id)
        rows=self.store.shift_sessions_v2(shift)
        self.assertEqual(len(rows),1)
        self.assertTrue(rows[0]["start"]["historical"])
        report=build_roster_shift_text(self.store,shift)
        self.assertIn("HISTORY ONLY",report)
        self.assertIn("ΙΣΤΟΡΙΚΗ ΚΑΤΑΧΩΡΙΣΗ",report)
        found=self.store.search_personnel_sessions(person_query="999002")
        self.assertEqual(len(found),1)
        self.assertTrue(found[0]["historical"])
        self.assertEqual(self.store.search_personnel_sessions(position="2"),[])
        self.assertEqual(self.store.search_personnel_sessions(min_duration_minutes=25),[])
        self.assertEqual(len(SharedEventStore(self.store.root).search_personnel_sessions(person_query="999002")),1)

    def test_pdf_regeneration_does_not_touch_live_booth(self):
        self.add()
        from PySide6.QtWidgets import QApplication
        from position_tracking_pdf import create_shift_pdf
        app=QApplication.instance() or QApplication([])
        before=self.store.active_all()
        path=self.store.reports/"synthetic.pdf"
        self.assertEqual(create_shift_pdf(self.store,self.store.get_shift(self.shift_id),target=path),path)
        self.assertTrue(path.read_bytes().startswith(b"%PDF"))
        self.assertEqual(self.store.active_all(),before)

    def test_five_live_approved_positions_remain_five_report_rows(self):
        from position_tracking_personnel import PersonnelRecord
        shift = self.store.get_shift(self.shift_id)
        people=[PersonnelRecord(str(999010+i),'TEST','LIVE',str(i)) for i in range(5)]
        shift['approved']=[p.agms for p in people]
        self.store._store_shift_snapshot(shift)
        for i,person in enumerate(people):
            self.store.start(person,str(i+1),'ΕΙΣΟΔΟΣ',when=self.base+timedelta(minutes=i))
        rows=self.store.shift_sessions_v2(shift)
        self.assertEqual(len(rows),5)
        self.assertEqual(len(self.store.active_all()),5)
        report=build_roster_shift_text(self.store,shift)
        for i in range(1,6):
            self.assertIn('ΘΕΣΗ '+str(i),report)

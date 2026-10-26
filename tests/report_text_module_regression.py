"""Pure formatter compatibility, escaping and boundary-date cases."""
from datetime import date, datetime
from pathlib import Path
import os
import subprocess
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import position_tracking as legacy
import position_tracking_report_text as reports

class Source:
    def __init__(self, sessions=()): self.sessions = list(sessions)
    def shift_sessions(self, day, cutoff): return datetime(2026,10,15,10), datetime(2026,10,16,10), self.sessions
    def shift_sessions_v2(self, shift): return self.sessions
    def roster_sessions(self, *args): return self.sessions

class ReportTextContract(unittest.TestCase):
    def test_exports_are_same_objects(self):
        for name in ('build_shift_text','build_roster_shift_text','build_shift_html','shift_report_title','_format_seconds'):
            self.assertIs(getattr(legacy,name),getattr(reports,name))
    def test_empty_and_escaped_html(self):
        self.assertIn('Δεν υπάρχουν καταχωρίσεις',reports.build_shift_text(Source(),date(2026,10,15),'10:00'))
        shift={'version':2,'start_at':'2026-10-15T10:00:00','approved':['<01&>']}
        html=reports.build_roster_shift_html(Source(),shift)
        self.assertIn('&lt;01&amp;&gt;',html)
        self.assertNotIn('<01&>',html)
        self.assertIn('Χωρίς καταχώριση θέσης',html)
    def test_open_closed_and_negative_durations(self):
        start=datetime(2026,10,15,10)
        item={'start':{'agms':'001','full_name':'ΟΝΟΜΑ','rank':'Αρχ.','position':'1','direction':'ΕΞΟΔΟΣ'},'start_dt':start,'end_dt':datetime(2026,10,15,11,30)}
        text=reports.build_shift_text(Source([item]),date(2026,10,15),'10:00')
        self.assertIn('Σύνολο ΕΞΟΔΟΣ: 01:30',text)
        item['end_dt']=None
        self.assertIn('ΑΝΟΙΚΤΗ',reports.build_shift_text(Source([item]),date(2026,10,15),'10:00'))
        self.assertEqual(reports._duration_text(start,datetime(2026,10,15,9)),'00:00')
        self.assertEqual(reports._format_seconds(90061),'25:01')
    def test_title_month_and_year_boundaries(self):
        for start,end,expected in [('2026-10-15','2026-10-16','15-16 Οκτωβρίου 2026'),('2026-10-31','2026-11-01','31 Οκτωβρίου - 01 Νοεμβρίου 2026'),('2026-12-31','2027-01-01','31 Δεκεμβρίου 2026 - 01 Ιανουαρίου 2027')]:
            self.assertIn(expected,reports.shift_report_title({'start_at':start,'end_at':end}))
    def test_standalone_without_entry_qt_or_document_libraries(self):
        code="import sys;sys.modules.update({k:None for k in ['position_tracking','PySide6','docx','openpyxl']});import position_tracking_report_text"
        p=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)

if __name__=='__main__':unittest.main()

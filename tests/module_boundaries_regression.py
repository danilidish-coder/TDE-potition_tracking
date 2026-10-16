"""Extracted services must be usable without the application entry or UI."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

class IndependentServices(unittest.TestCase):
    def test_standalone_services_do_not_import_entry_or_qt_eagerly(self):
        modules=['position_tracking_settings','position_tracking_personnel','position_tracking_theme','position_tracking_report_text','position_tracking_pdf','position_tracking_documents']
        code="import sys,importlib;sys.modules['position_tracking']=None;sys.modules['PySide6']=None;"+repr(modules)+";[importlib.import_module(m) for m in "+repr(modules)+"]"
        result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_word_document_roundtrip(self):
        import tempfile
        from docx import Document
        from position_tracking_documents import create_shift_docx
        class EmptySource:
            def shift_sessions_v2(self, shift): return []
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'report.docx'
            create_shift_docx(EmptySource(), {'version':2,'start_at':'2026-10-15T10:00:00','approved':['001']}, target=path)
            text='\n'.join(p.text for p in Document(path).paragraphs)
            self.assertIn('001',text)
            self.assertIn('Χωρίς καταχώριση',text)

    def test_pdf_facade_identity_and_missing_qt_failure(self):
        import position_tracking as facade
        import position_tracking_pdf as pdf
        self.assertIs(facade.create_shift_pdf,pdf.create_shift_pdf)
        self.assertIs(facade.create_personnel_history_pdf,pdf.create_personnel_history_pdf)
        code="import sys;sys.modules['PySide6']=None;import position_tracking_pdf as p;\ntry:p.create_shift_pdf(None,{})\nexcept RuntimeError as e:assert 'PDF' in str(e)\nelse:raise AssertionError('missing Qt must fail')"
        result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(ROOT/'src')),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()

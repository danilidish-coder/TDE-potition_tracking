"""Real watchdog captures blocked Qt and worker locations without data contents."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import json
import sys
import tempfile
import threading
import time
import unittest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_diagnostics import RuntimeDiagnostics, process_resources, start_runtime_diagnostics

class RuntimeDiagnosticsRegression(unittest.TestCase):
    def wait(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate(): return
            QTest.qWait(10)
        self.fail('diagnostic event not observed')

    def test_gui_stall_and_recovery_capture_stack_without_personal_content(self):
        app = QApplication.instance() or QApplication([])
        sensitive = 'PRIVATE_PERSONNEL_VALUE_MUST_NEVER_BE_LOGGED'
        with tempfile.TemporaryDirectory() as directory:
            d = RuntimeDiagnostics(Path(directory), gui_timeout=.15, interval=.02, sample_interval=.1)
            timer = QTimer(); timer.timeout.connect(d.heartbeat); timer.start(20)
            try:
                self.wait(lambda:d.available)
                def block_gui():
                    secret = sensitive
                    time.sleep(.4)
                    self.assertEqual(secret, sensitive)
                QTimer.singleShot(0, block_gui)
                self.wait(lambda:'gui_recovered' in d.path.read_text())
            finally: timer.stop(); d.stop(wait=True)
            text = d.path.read_text(); events = [json.loads(line) for line in text.splitlines()]
            self.assertIn('gui_stall', [e['event'] for e in events])
            self.assertIn('block_gui', text); self.assertNotIn(sensitive, text)
            self.assertNotIn(str(ROOT), text); self.assertFalse(d.thread.is_alive())

    def test_worker_age_is_not_reset_by_gui_heartbeat_and_rotation_is_bounded(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            d = RuntimeDiagnostics(Path(directory), gui_timeout=2, worker_timeout=.1,
                                   interval=.01, sample_interval=.02, max_bytes=1200, backups=2)
            try:
                self.wait(lambda:d.available)
                deadline = time.monotonic() + .4
                observed = False
                while time.monotonic() < deadline:
                    d.heartbeat({'offline':123}, {'network':1})
                    QTest.qWait(10)
                    observed |= any('worker_stall' in p.read_text() for p in Path(directory).glob('*'))
                self.assertTrue(observed)
            finally:d.stop(wait=True)
            files = list(Path(directory).glob('*')); self.assertLessEqual(len(files), 3)
            self.assertLess(sum(f.stat().st_size for f in files), 15000)

    def test_unwritable_destination_does_not_crash_or_leak_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'file'; file.write_text('existing')
            d = RuntimeDiagnostics(file)
            d.thread.join(2)
            self.assertFalse(d.thread.is_alive()); self.assertFalse(d.available)
            self.assertEqual(file.read_text(), 'existing')

    def test_real_process_resources_and_qt_installation(self):
        app = QApplication.instance() or QApplication([])
        self.assertGreater(process_resources()['rss_bytes'], 0)
        self.assertGreater(process_resources()['handles'], 0)
        with tempfile.TemporaryDirectory() as directory:
            w = QWidget(); d = start_runtime_diagnostics(app, w, Path(directory))
            try:self.wait(lambda:d.available)
            finally:w._runtime_diagnostics_timer.stop(); d.stop(wait=True); w.close()

if __name__ == '__main__': unittest.main()

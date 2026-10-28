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
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QWidget
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_diagnostics import RuntimeDiagnostics, process_resources, start_runtime_diagnostics

class RuntimeDiagnosticsRegression(unittest.TestCase):
    @staticmethod
    def pump():
        QApplication.processEvents()
        # Yield the Python GIL as the real Qt event loop does. A tight qWait
        # loop can starve the Python diagnostics writer on Windows.
        time.sleep(.01)

    def wait(self, predicate, seconds=3):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate(): return
            self.pump()
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

    def test_worker_age_is_not_reset_by_gui_heartbeat(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            d = RuntimeDiagnostics(Path(directory), gui_timeout=2, worker_timeout=.1,
                                   interval=.01, sample_interval=.02)
            try:
                self.wait(lambda:d.available)
                deadline = time.monotonic() + .4
                while time.monotonic() < deadline:
                    d.heartbeat({'offline':123}, {'network':1})
                    self.pump()
            finally:d.stop(wait=True)
            events = [json.loads(line) for line in d.path.read_text().splitlines()]
            stalls = [event for event in events if event['event']=='worker_stall']
            self.assertEqual(len(stalls), 1)
            self.assertGreaterEqual(stalls[0]['workers']['offline'], .1)

    def test_rotation_is_bounded_and_records_remain_valid_after_writer_closes(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            d = RuntimeDiagnostics(Path(directory), gui_timeout=2, interval=.01,
                                   sample_interval=.02, max_bytes=1200, backups=2)
            with patch('position_tracking_diagnostics.process_resources', wraps=process_resources) as probe:
                try:
                    self.wait(lambda:d.available)
                    deadline = time.monotonic() + 5
                    while probe.call_count < 30 and time.monotonic() < deadline:
                        d.heartbeat(); self.pump()
                finally:d.stop(wait=True)
                # Drive actual writes, not an assumed scheduler throughput in
                # a fixed 400ms window. All real resource probes still execute.
                self.assertGreaterEqual(probe.call_count, 30)
            # Never enumerate and tail a rotating writer concurrently: the old
            # test raced a legitimate rename. Assert every retained record here.
            self.assertFalse(d.thread.is_alive())
            files = list(Path(directory).glob('*')); self.assertGreaterEqual(len(files), 2)
            self.assertLessEqual(len(files), 3)
            self.assertLess(sum(f.stat().st_size for f in files), 15000)
            for file in files:
                for line in file.read_text().splitlines(): self.assertIn('event', json.loads(line))

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

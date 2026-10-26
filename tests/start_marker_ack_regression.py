"""Ambiguous SMB active-marker commit must not erase durable START history."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import position_tracking as application


class StartAcknowledgementContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = application.SharedEventStore(self.temporary.name)
        self.person = application.PersonnelRecord('999001', 'TEST', 'START', 'ACK')
        self.when = datetime(2026, 10, 15, 10, 0, 0)
        self.operation = 'test-lost-active-ack'

    def tearDown(self):
        self.temporary.cleanup()

    def start(self):
        return self.store.start(self.person, '1', 'ΕΙΣΟΔΟΣ', when=self.when, event_id=self.operation)

    def test_failure_before_replace_still_has_no_phantom_history(self):
        original = self.store._atomic_json
        def fail_before(path, data):
            if path == self.store._active_path(self.person.agms):
                raise OSError('before marker commit')
            original(path, data)
        self.store._atomic_json = fail_before
        with self.assertRaises(OSError):
            self.start()
        self.assertIsNone(self.store.get_active(self.person.agms))
        self.assertEqual(self.store.iter_all_events(), [])

    def exercise_committed_marker(self, unreadable):
        original_write = self.store._atomic_json
        original_read = Path.read_text
        active = self.store._active_path(self.person.agms)
        committed = []
        def commit_then_fail(path, data):
            original_write(path, data)
            if path == active:
                committed.append(True)
                raise OSError('lost acknowledgement after marker commit')
        def read(path, *args, **kwargs):
            if unreadable and committed and path == active:
                raise OSError('shared marker temporarily unreadable')
            return original_read(path, *args, **kwargs)
        self.store._atomic_json = commit_then_fail
        with patch.object(Path, 'read_text', read):
            with self.assertRaises(OSError):
                self.start()
        self.store._atomic_json = original_write
        self.assertTrue(committed)
        self.assertEqual([e['event_id'] for e in self.store.iter_all_events()], [self.operation])
        # Reconstruct the client/store after the outage, then retry original ID.
        self.store = application.SharedEventStore(self.temporary.name)
        self.assertEqual(self.start()['event_id'], self.operation)
        self.assertEqual(self.start()['event_id'], self.operation)
        other = application.PersonnelRecord('999002', 'TEST', 'OTHER', 'USER')
        with self.assertRaises(ValueError):
            self.store.start(other, '1', 'ΕΞΟΔΟΣ', when=self.when)
        end = self.store.end(self.person, when=self.when + timedelta(minutes=5),
                             expected_start_event_id=self.operation, event_id='test-end-ack')
        events = self.store.iter_all_events()
        self.assertEqual(len(events), 2)
        self.assertEqual(end['start_event_id'], self.operation)
        self.assertEqual(next(e for e in events if e['kind'] == 'START')['timestamp'], self.when.isoformat())
        self.assertIsNone(self.store.get_active(self.person.agms))

    def test_lost_ack_after_replace_preserves_history(self):
        self.exercise_committed_marker(False)

    def test_lost_ack_and_unreadable_marker_preserve_history(self):
        self.exercise_committed_marker(True)


if __name__ == '__main__':
    unittest.main()

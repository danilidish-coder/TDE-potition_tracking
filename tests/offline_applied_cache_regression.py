"""Atomic replay/cache state across SQLite faults, restarts and two replayers."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Event
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking import OfflineJournal, PersonnelRecord, SharedEventStore


class AppliedCacheContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = SharedEventStore(self.root / 'central')
        self.journal = OfflineJournal(self.root / 'local')
        self.person = PersonnelRecord('999004', 'TEST', 'ATOMIC', 'CACHE')

    def tearDown(self):
        self.temporary.cleanup()

    def fail_observed_writes(self):
        with self.journal._db() as db:
            db.execute("CREATE TRIGGER fail_observed BEFORE INSERT ON observed "
                       "BEGIN SELECT RAISE(ABORT, 'injected cache commit failure'); END")

    def restore_observed_writes(self):
        with self.journal._db() as db:
            db.execute('DROP TRIGGER fail_observed')

    def sync(self):
        return self.journal.sync(self.store, PersonnelRecord)

    def test_start_cache_fault_rolls_back_applied_and_retries_same_id(self):
        operation = self.journal.enqueue('START', self.person, '3', 'ΕΞΟΔΟΣ')
        self.fail_observed_writes()
        with self.assertRaises(sqlite3.IntegrityError):
            self.sync()
        self.journal = OfflineJournal(self.root / 'local')
        self.assertEqual(self.journal.pending_count(), 1)
        self.assertEqual(self.journal.local_active(self.person.agms)['event_id'], operation['operation_id'])
        self.assertEqual(self.store.get_active(self.person.agms)['event_id'], operation['operation_id'])
        self.restore_observed_writes()
        self.assertEqual(self.sync()['applied'], [operation['operation_id']])
        self.assertEqual(self.journal.pending_count(), 0)
        self.assertEqual(self.journal.local_active(self.person.agms)['event_id'], operation['operation_id'])
        self.assertEqual(len(self.store.iter_all_events()), 1)

    def test_end_cache_fault_rolls_back_applied_without_resurrecting_start(self):
        self.journal.enqueue('START', self.person, '3', 'ΕΞΟΔΟΣ')
        self.sync()
        operation = self.journal.enqueue('END', self.person)
        self.fail_observed_writes()
        with self.assertRaises(sqlite3.IntegrityError):
            self.sync()
        self.journal = OfflineJournal(self.root / 'local')
        self.assertEqual(self.journal.pending_count(), 1)
        self.assertIsNone(self.journal.local_active(self.person.agms))
        self.assertIsNone(self.store.get_active(self.person.agms))
        self.restore_observed_writes()
        self.assertEqual(self.sync()['applied'], [operation['operation_id']])
        self.assertIsNone(self.journal.local_active(self.person.agms))
        self.assertEqual(len(self.store.iter_all_events()), 2)

    def test_delayed_start_response_cannot_overwrite_a_later_end(self):
        operation = self.journal.enqueue('START', self.person, '3', 'ΕΞΟΔΟΣ')
        committed, release = Event(), Event()
        central = self.store

        class SlowStartResponse:
            def start(self, *args, **kwargs):
                event = central.start(*args, **kwargs)
                committed.set()
                if not release.wait(10):
                    raise TimeoutError('test response barrier not released')
                return event

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.journal.sync, SlowStartResponse(), PersonnelRecord)
            try:
                self.assertTrue(committed.wait(10))
                other = OfflineJournal(self.root / 'local')
                self.assertEqual(other.sync(self.store, PersonnelRecord)['applied'], [operation['operation_id']])
                other.enqueue('END', self.person)
                self.assertEqual(len(other.sync(self.store, PersonnelRecord)['applied']), 1)
                self.assertIsNone(other.local_active(self.person.agms))
            finally:
                release.set()
            self.assertEqual(future.result(timeout=10)['applied'], [])
        self.assertIsNone(self.journal.local_active(self.person.agms))
        self.assertEqual(len(self.store.iter_all_events()), 2)

    def test_delayed_empty_read_cannot_erase_a_new_applied_start(self):
        revision = self.journal.observation_revision(self.person.agms)
        other = OfflineJournal(self.root / 'local')
        operation = other.enqueue('START', self.person, '14', 'ΕΞΟΔΟΣ')
        other.sync(self.store, PersonnelRecord)
        self.assertFalse(self.journal.remember(self.person.agms, None, expected_revision=revision))
        self.assertEqual(self.journal.local_active(self.person.agms)['event_id'], operation['operation_id'])
        current = self.journal.observation_revision(self.person.agms)
        self.assertTrue(self.journal.remember(self.person.agms, self.store.get_active(self.person.agms), expected_revision=current))
        self.assertEqual(len(self.store.iter_all_events()), 1)


if __name__ == '__main__':
    unittest.main()

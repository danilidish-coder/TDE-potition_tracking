"""SMB boundary model: a stale client resumes after losing its server locks.

Only the stale instance's officer_lock is replaced: the fixture models server
lock loss while its old Python call stack is still alive. Other clients use
real OS locks/SQLite, real store code and synthetic temporary event files.
These assertions are safety requirements, not expected failures.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore


@contextmanager
def lost_server_lock(*args, **kwargs):
    # The old worker still believes it is inside its lock contexts, although
    # the server has released those locks when its SMB session disconnected.
    yield


class StaleWorkerContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-stale-worker-")
        self.addCleanup(self.temp.cleanup)
        self.stale = SharedEventStore(self.temp.name)
        self.first = PersonnelRecord("999001", "TEST", "SYNTHETIC", "FIRST")
        self.second = PersonnelRecord("999002", "TEST", "SYNTHETIC", "SECOND")
        self.when = datetime(2026, 10, 26, 23, 59)
        self.blocked = threading.Event()
        self.resume = threading.Event()
        self.addCleanup(self.resume.set)

    def block_stale_write(self, predicate):
        original = self.stale._atomic_json
        def write(path, event):
            if predicate(path, event):
                self.blocked.set()
                if not self.resume.wait(10):
                    raise AssertionError("Fixture did not release stale worker")
            original(path, event)
        self.stale._atomic_json = write
        self.stale.officer_lock = lost_server_lock

    def test_stale_start_must_not_claim_booth_taken_after_lock_loss(self):
        self.block_stale_write(lambda path, event: path.is_relative_to(self.stale.events))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.stale.start, self.first, "1", "ΕΙΣΟΔΟΣ",
                                 when=self.when, event_id="stale-start")
            try:
                self.assertTrue(self.blocked.wait(3), "START did not reach raw-file boundary")
                replacement = SharedEventStore(self.temp.name)
                current = replacement.start(self.second, "1", "ΕΞΟΔΟΣ",
                                            when=self.when + timedelta(minutes=1), event_id="current-start")
            finally:
                self.resume.set()
            future.result(timeout=5)
        reopened = SharedEventStore(self.temp.name)
        active = reopened.active_all()
        self.assertEqual(len([item for item in active if item["position"] == "1"]), 1,
                         "A stale START must not create two live occupants of one physical booth")
        self.assertEqual(active[0]["event_id"], current["event_id"])

    def test_stale_end_must_not_unlink_replacement_start(self):
        start = self.stale.start(self.first, "1", "ΕΙΣΟΔΟΣ", when=self.when,
                                 event_id="original-start")
        self.block_stale_write(lambda path, event: path.parent == self.stale.pending_index)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.stale.end, self.first,
                                 when=self.when + timedelta(minutes=1), event_id="original-end",
                                 expected_start_event_id=start["event_id"])
            try:
                self.assertTrue(self.blocked.wait(3), "END did not reach receipt boundary")
                replacement = SharedEventStore(self.temp.name)
                current = replacement.start(self.first, "2", "ΕΞΟΔΟΣ",
                                            when=self.when + timedelta(minutes=2), event_id="replacement-start")
            finally:
                self.resume.set()
            future.result(timeout=5)
        reopened = SharedEventStore(self.temp.name)
        active = reopened.get_active(self.first.agms)
        self.assertIsNotNone(active, "A stale END must not remove a later confirmed START")
        self.assertEqual(active["event_id"], current["event_id"])


if __name__ == "__main__":
    unittest.main()

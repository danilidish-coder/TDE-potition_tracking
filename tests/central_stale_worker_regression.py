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

    def test_stale_start_same_agms_cannot_replace_newer_claim_or_report(self):
        self.block_stale_write(lambda path, event: path.is_relative_to(self.stale.events))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.stale.start, self.first, "1", "ΕΙΣΟΔΟΣ",
                                 when=self.when, event_id="stale-start")
            try:
                self.assertTrue(self.blocked.wait(3))
                replacement = SharedEventStore(self.temp.name)
                replacement.start(self.first, "2", "ΕΞΟΔΟΣ", when=self.when + timedelta(minutes=1),
                                  event_id="current-start")
            finally:
                self.resume.set()
            self.assertTrue(future.result(timeout=5)["superseded"])
        reopened = SharedEventStore(self.temp.name)
        self.assertEqual(reopened.get_active(self.first.agms)["event_id"], "current-start")
        self.assertEqual([e["event_id"] for e in reopened.iter_all_events()], ["current-start"])
        raw = [path for path in reopened.events.rglob("*.json") if "stale-start" in path.name]
        self.assertEqual(len(raw), 1, "Keep superseded raw evidence; do not delete it")
        self.assertEqual(reopened._position_operation("stale-start")["state"], "ABORTED")

    def test_stale_end_before_commit_cannot_close_or_report_over_replacement(self):
        self.stale.start(self.first, "1", "ΕΙΣΟΔΟΣ", when=self.when, event_id="original-start")
        self.block_stale_write(lambda path, event: path.is_relative_to(self.stale.events))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.stale.end, self.first, when=self.when + timedelta(minutes=1),
                                 event_id="stale-end", expected_start_event_id="original-start")
            try:
                self.assertTrue(self.blocked.wait(3))
                replacement = SharedEventStore(self.temp.name)
                replacement.end(self.first, when=self.when + timedelta(minutes=2), event_id="current-end")
                replacement.start(self.first, "2", "ΕΞΟΔΟΣ", when=self.when + timedelta(minutes=3),
                                  event_id="current-start")
            finally:
                self.resume.set()
            self.assertTrue(future.result(timeout=5)["superseded"])
        reopened = SharedEventStore(self.temp.name)
        self.assertEqual(reopened.get_active(self.first.agms)["event_id"], "current-start")
        self.assertEqual([e["event_id"] for e in reopened.iter_all_events() if e["kind"] == "END"], ["current-end"])
        self.assertEqual(reopened.search_personnel_sessions()[0]["end_event_id"], "current-end")

    def test_retry_same_operation_id_has_new_attempt_token(self):
        self.block_stale_write(lambda path, event: path.is_relative_to(self.stale.events))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.stale.start, self.first, "1", "ΕΙΣΟΔΟΣ",
                                 when=self.when, event_id="shared-operation")
            try:
                self.assertTrue(self.blocked.wait(3))
                old_token = self.stale._position_operation("shared-operation")["attempt"]
                replacement = SharedEventStore(self.temp.name)
                replacement.start(self.first, "1", "ΕΙΣΟΔΟΣ", when=self.when + timedelta(days=1),
                                  event_id="shared-operation")
                new_token = replacement._position_operation("shared-operation")["attempt"]
                self.assertNotEqual(old_token, new_token)
            finally:
                self.resume.set()
            self.assertTrue(future.result(timeout=5)["superseded"])
        self.assertFalse(replacement._abort_position_event("shared-operation", old_token))
        reopened = SharedEventStore(self.temp.name)
        self.assertEqual(reopened.get_active(self.first.agms)["event_id"], "shared-operation")
        self.assertEqual(reopened.get_active(self.first.agms)["timestamp"], self.when.isoformat())
        self.assertEqual(len(reopened.iter_all_events()), 1)

    def test_missing_active_projection_does_not_erase_confirmed_claim(self):
        start = self.stale.start(self.first, "1", "ΕΙΣΟΔΟΣ", when=self.when, event_id="confirmed-start")
        self.stale._active_path(self.first.agms).unlink()
        reopened = SharedEventStore(self.temp.name)
        self.assertEqual(reopened.get_active(self.first.agms)["event_id"], start["event_id"])
        self.assertEqual(len(reopened.active_all()), 1)


if __name__ == "__main__":
    unittest.main()

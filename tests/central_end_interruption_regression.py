"""Issue #10 Phase A gate: durable END must survive a receipt interruption.

Uses synthetic data in a temporary directory; never opens deployment settings,
local outboxes, or a production share. The recovery test intentionally fails
on approved baseline 4340c418; do not mark expectedFailure or weaken it.
"""
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore


class CentralEndInterruption(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tde-issue10-end-")
        self.addCleanup(self.directory.cleanup)
        self.store = SharedEventStore(self.directory.name)
        self.person = PersonnelRecord("999001", "TEST", "SYNTHETIC", "AUDIT")
        self.start_time = datetime(2026, 10, 27, 12)
        self.end_time = self.start_time + timedelta(minutes=10)
        self.start_id = "issue10-start"
        self.end_id = "issue10-end"
        self.store.start(self.person, "1", "ΕΙΣΟΔΟΣ", when=self.start_time,
                         event_id=self.start_id)

    def end(self, store, event_id=None):
        return store.end(self.person, when=self.end_time,
                         expected_start_event_id=self.start_id,
                         event_id=event_id or self.end_id)

    def interrupt_receipt(self):
        original = self.store._atomic_json

        def interrupted(path, data):
            if path.parent == self.store.pending_index:
                raise OSError("synthetic disconnect before END receipt")
            original(path, data)

        self.store._atomic_json = interrupted
        with self.assertRaisesRegex(OSError, "synthetic disconnect"):
            self.end(self.store)
        self.assertEqual(len([event for event in self.store.iter_all_events()
                              if event["kind"] == "END"]), 1)

    def assert_completed_once(self, store):
        self.assertIsNone(store.get_active(self.person.agms),
                          "Durable END must release the position after recovery")
        history = store.search_personnel_sessions(person_query=self.person.agms)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["start_event_id"], self.start_id)
        self.assertEqual(history[0]["end_event_id"], self.end_id)
        self.assertEqual(history[0]["end_at"], self.end_time.isoformat())
        self.assertEqual(len([event for event in store.iter_all_events()
                              if event["kind"] == "END"]), 1)

    def test_normal_end_survives_reopen(self):
        self.end(self.store)
        self.assert_completed_once(SharedEventStore(self.directory.name))

    def test_exact_original_id_and_time_can_repair_interruption(self):
        self.interrupt_receipt()
        reopened = SharedEventStore(self.directory.name)
        self.end(reopened)
        self.assert_completed_once(reopened)

    def test_reopen_recovers_durable_end_without_local_queue(self):
        self.interrupt_receipt()
        reopened = SharedEventStore(self.directory.name)
        self.assert_completed_once(reopened)

    def test_new_client_must_not_write_second_end_for_same_start(self):
        self.interrupt_receipt()
        reopened = SharedEventStore(self.directory.name)
        try:
            self.end(reopened, "issue10-new-client-end")
        except ValueError:
            pass  # Rejecting another END of an already completed START is safe.
        ends = [event for event in reopened.iter_all_events() if event["kind"] == "END"]
        self.assertEqual(len(ends), 1, "One START must have only one durable END")
        self.assert_completed_once(reopened)


if __name__ == "__main__":
    unittest.main()

"""Real central-store fault boundaries, immutable IDs, legacy evidence and races."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore
from position_tracking_store_io import BusyError


class RecoveryContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-central-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.store = SharedEventStore(self.temp.name)
        self.person = PersonnelRecord("999001", "TEST", "SYNTHETIC", "FIRST")
        self.other = PersonnelRecord("999002", "TEST", "SYNTHETIC", "SECOND")
        self.when = datetime(2026, 10, 26, 23, 59)

    def start(self, **kwargs):
        return self.store.start(self.person, "1", "ΕΙΣΟΔΟΣ", when=self.when,
                                event_id="start-original", **kwargs)

    def end(self, **kwargs):
        return self.store.end(self.person, when=self.when + timedelta(minutes=2),
                              expected_start_event_id="start-original",
                              event_id="end-original", **kwargs)

    def reopen(self):
        self.store = SharedEventStore(self.temp.name)
        return self.store

    def events(self, kind):
        return [event for event in self.store.iter_all_events() if event["kind"] == kind]

    def interrupt_json(self, predicate, committed=False):
        original = self.store._atomic_json
        def write(path, event):
            if predicate(path, event):
                if committed:
                    original(path, event)
                raise OSError("synthetic interrupted acknowledgement")
            original(path, event)
        self.store._atomic_json = write

    def assert_closed(self):
        self.assertIsNone(self.store.get_active(self.person.agms))
        self.assertEqual(self.store.active_all(), [])
        self.assertEqual(len(self.events("END")), 1)
        rows = self.store.search_personnel_sessions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["end_event_id"], "end-original")
        self.assertEqual(rows[0]["start_at"], self.when.isoformat())
        self.assertEqual(rows[0]["end_at"], (self.when + timedelta(minutes=2)).isoformat())

    def test_end_raw_rename_ack_lost_cross_midnight(self):
        self.start()
        self.interrupt_json(lambda path, e: path.is_relative_to(self.store.events) and e["kind"] == "END", True)
        with self.assertRaises(OSError):
            self.end(end_reason="ORIGINAL_REASON", end_officer=self.other)
        self.reopen()
        self.assert_closed()
        replay = self.store.end(self.person, when=self.when + timedelta(days=3),
                                event_id="end-original", expected_start_event_id="start-original")
        self.assertEqual(replay["end_reason"], "ORIGINAL_REASON")
        self.assertEqual(replay["end_officer"]["agms"], self.other.agms)
        self.assert_closed()

    def test_end_precommit_failure_keeps_position_active(self):
        self.start()
        self.interrupt_json(lambda path, e: path.is_relative_to(self.store.events) and e["kind"] == "END")
        with self.assertRaises(OSError):
            self.end()
        self.reopen()
        self.assertEqual(self.store.get_active(self.person.agms)["event_id"], "start-original")
        self.assertEqual(self.events("END"), [])
        self.end()
        self.assert_closed()

    def test_end_active_unlink_failure_recovers(self):
        self.start()
        original = Path.unlink
        def unlink(path, *args, **kwargs):
            if path.parent == self.store.active:
                raise OSError("synthetic active unlink failure")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", unlink), self.assertRaises(OSError):
            self.end()
        self.reopen()
        self.assert_closed()

    def test_end_index_failure_does_not_block_reused_booth(self):
        self.start()
        self.store._store_personnel_session = lambda *_: (_ for _ in ()).throw(BusyError("history busy"))
        self.assertTrue(self.end()["session_index_pending"])
        self.store.start(self.other, "1", "ΕΞΟΔΟΣ", when=self.when + timedelta(minutes=3), event_id="next-start")
        self.reopen()
        self.assertEqual(len(self.events("END")), 1)
        self.assertEqual(len(self.store.search_personnel_sessions()), 1)
        self.assertEqual(self.store.get_active(self.other.agms)["event_id"], "next-start")

    def test_start_raw_rename_ack_lost_recovers_without_original_client(self):
        self.interrupt_json(lambda path, e: path.is_relative_to(self.store.events), True)
        with self.assertRaises(OSError):
            self.start()
        self.reopen()
        active = self.store.get_active(self.person.agms)
        self.assertEqual(active["event_id"], "start-original")
        self.assertEqual(active["timestamp"], self.when.isoformat())
        with self.assertRaises(ValueError):
            self.store.start(self.other, "1", "ΕΞΟΔΟΣ", event_id="different-start")
        with self.assertRaises(ValueError):
            self.store.start(self.person, "2", "ΕΞΟΔΟΣ", event_id="another-start")
        replay = self.store.start(self.person, "1", "ΕΙΣΟΔΟΣ", when=self.when + timedelta(days=3), event_id="start-original")
        self.assertEqual(replay["timestamp"], active["timestamp"])
        self.assertEqual(len(self.events("START")), 1)

    def test_start_marker_lost_ack_and_reopen(self):
        self.interrupt_json(lambda path, e: path.parent == self.store.active, True)
        with self.assertRaises(OSError):
            self.start()
        self.reopen()
        self.assertEqual(self.store.get_active(self.person.agms)["event_id"], "start-original")
        self.assertEqual(len(self.events("START")), 1)

    def test_closed_start_retry_across_day_never_resurrects(self):
        self.start()
        self.end()
        self.reopen()
        self.store.start(self.person, "1", "ΕΙΣΟΔΟΣ", when=self.when + timedelta(days=1), event_id="start-original")
        self.assert_closed()
        self.assertEqual(len(self.events("START")), 1)

    def test_reusing_id_for_different_booth_is_rejected(self):
        self.start()
        with self.assertRaises(BusyError):
            self.store.start(self.person, "2", "ΕΞΟΔΟΣ", event_id="start-original")
        self.assertEqual(self.store.get_active(self.person.agms)["position"], "1")

    def test_operation_id_is_unique_across_people(self):
        self.start()
        with self.assertRaises(BusyError):
            self.store.start(self.other, "2", "ΕΙΣΟΔΟΣ", event_id="start-original")
        self.assertIsNone(self.store.get_active(self.other.agms))

    def test_stale_end_cannot_close_replacement(self):
        self.start()
        self.end()
        replacement = self.store.start(self.person, "2", "ΕΞΟΔΟΣ", event_id="replacement-start")
        with self.assertRaises(BusyError):
            self.end()
        with self.assertRaises(BusyError):
            self.store.end(self.person, expected_start_event_id="start-original", event_id="replacement-end")
        self.assertEqual(self.store.get_active(self.person.agms)["event_id"], replacement["event_id"])

    def test_fifteen_clients_retry_interrupted_end_once(self):
        self.start()
        self.interrupt_json(lambda path, e: path.parent == self.store.pending_index)
        with self.assertRaises(OSError):
            self.end()
        def retry(i):
            store = SharedEventStore(self.temp.name)
            try:
                store.end(self.person, expected_start_event_id="start-original", event_id=f"retry-{i}")
            except ValueError:
                return "already closed"
            return "ended"
        with ThreadPoolExecutor(max_workers=15) as pool:
            self.assertEqual(list(pool.map(retry, range(15))), ["already closed"] * 15)
        self.reopen()
        self.assert_closed()

    def test_fifteen_clients_same_booth_have_one_winner(self):
        def claim(i):
            store = SharedEventStore(self.temp.name)
            person = PersonnelRecord(str(900000 + i), "TEST", "SYNTHETIC", str(i))
            try:
                store.start(person, "1", "ΕΙΣΟΔΟΣ" if i % 2 else "ΕΞΟΔΟΣ", event_id=f"claim-{i}")
            except ValueError:
                return False
            return True
        with ThreadPoolExecutor(max_workers=15) as pool:
            self.assertEqual(sum(pool.map(claim, range(15))), 1)
        self.reopen()
        self.assertEqual(len(self.events("START")), 1)
        self.assertEqual(len(self.store.active_all()), 1)

    def legacy_index_absent(self):
        # Simulate an old central share with immutable raw JSON but no new index.
        with self.store._shift_db_connect() as db:
            db.execute("DROP TABLE position_operations")
            db.execute("DELETE FROM meta WHERE key='position_events_index_v1'")

    def test_legacy_durable_end_without_any_new_recovery_index(self):
        start = self.start()
        end = {**start, "event_id": "end-original", "kind": "END", "start_event_id": start["event_id"],
               "timestamp": (self.when + timedelta(minutes=2)).isoformat()}
        self.store._atomic_json(self.store._event_path(end), end)
        self.legacy_index_absent()
        self.reopen()
        self.assert_closed()

    def test_legacy_start_without_active_marker_is_recovered(self):
        self.start()
        self.store._active_path(self.person.agms).unlink()
        self.legacy_index_absent()
        self.reopen()
        self.assertEqual(self.store.get_active(self.person.agms)["event_id"], "start-original")

    def test_unreadable_committed_evidence_fails_closed(self):
        start = self.start()
        Path(start["event_file"]).write_text("{broken", encoding="utf-8")
        # Trigger an unsettled recovery rather than relying on a settled marker.
        self.store._position_index_write("UPDATE position_operations SET settled=0")
        with self.assertRaises(ValueError):
            self.reopen()

    def test_recovery_limit_fails_closed(self):
        self.start()
        self.store._position_index_write("UPDATE position_operations SET settled=0")
        with patch.object(SharedEventStore, "POSITION_RECOVERY_LIMIT", 0), self.assertRaises(BusyError):
            self.reopen()

    def test_legacy_import_limit_fails_closed(self):
        self.start()
        self.legacy_index_absent()
        with patch.object(SharedEventStore, "LEGACY_RECOVERY_FILE_LIMIT", 0), self.assertRaises(BusyError):
            self.reopen()

    def test_end_cannot_precede_start(self):
        self.start()
        with self.assertRaises(ValueError):
            self.store.end(self.person, when=self.when - timedelta(seconds=1), event_id="invalid-time-end")
        self.assertEqual(self.events("END"), [])

    def test_precommit_retry_keeps_original_time_across_days(self):
        self.start()
        self.interrupt_json(lambda path, e: path.is_relative_to(self.store.events) and e["kind"] == "END")
        with self.assertRaises(OSError):
            self.end()
        self.reopen()
        self.store.end(self.person, when=self.when + timedelta(days=2),
                       event_id="end-original", expected_start_event_id="start-original")
        self.assert_closed()

    def test_precommit_end_retry_cannot_bypass_later_start_correction(self):
        self.when = self.when.replace(hour=12, minute=0)
        self.start()
        self.interrupt_json(lambda path, e: path.is_relative_to(self.store.events) and e["kind"] == "END")
        with self.assertRaises(OSError):
            self.end()
        self.reopen()
        self.store.correct_active_start(self.person.agms, self.when + timedelta(minutes=3),
                                        self.other, "Synthetic audited correction")
        with self.assertRaises(ValueError):
            self.store.end(self.person, when=self.when + timedelta(days=1), event_id="end-original",
                           expected_start_event_id="start-original")
        self.reopen()
        self.assertEqual(self.events("END"), [])
        self.assertIsNotNone(self.store.get_active(self.person.agms))

    def test_legacy_duplicate_end_evidence_blocks_recovery(self):
        self.start()
        ended = self.end()
        duplicate = {**ended, "event_id": "duplicate-end"}
        self.store._atomic_json(self.store._event_path(duplicate), duplicate)
        self.legacy_index_absent()
        with self.assertRaises(sqlite3.IntegrityError):
            self.reopen()
        self.assertEqual(len(self.events("END")), 2)  # Preserve both as evidence.

    def test_legacy_conflicting_starts_are_preserved_and_blocked(self):
        first = self.start()
        second = {**first, "event_id": "conflicting-start", "agms": self.other.agms}
        self.store._atomic_json(self.store._event_path(second), second)
        self.legacy_index_absent()
        with self.assertRaises(BusyError):
            self.reopen()
        self.assertEqual(len(self.events("START")), 2)

    def crash_after_raw_commit(self, kind):
        source = Path(__file__).resolve().parents[1] / "src"
        program = """
import os, sys
from datetime import datetime
sys.path.insert(0, sys.argv[1])
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord
store = SharedEventStore(sys.argv[2])
person = PersonnelRecord('999001', 'TEST', 'SYNTHETIC', 'FIRST')
original = store._atomic_json
def crash(path, event):
    original(path, event)
    if path.is_relative_to(store.events) and event['kind'] == sys.argv[3]:
        os._exit(77)
store._atomic_json = crash
if sys.argv[3] == 'START':
    store.start(person, '1', 'ΕΙΣΟΔΟΣ', when=datetime(2026,10,26,23,59), event_id='start-original')
else:
    store.end(person, when=datetime(2026,10,27,0,1), event_id='end-original', expected_start_event_id='start-original')
"""
        completed = subprocess.run([sys.executable, "-c", program, str(source), self.temp.name, kind],
                                   capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 77, completed.stderr)
        self.reopen()

    def test_process_death_after_start_event_recovers_and_releases_locks(self):
        self.crash_after_raw_commit("START")
        self.assertEqual(self.store.get_active(self.person.agms)["event_id"], "start-original")
        self.assertEqual(len(self.events("START")), 1)
        self.end()
        self.assert_closed()

    def test_process_death_after_end_event_recovers_and_releases_locks(self):
        self.start()
        self.crash_after_raw_commit("END")
        self.assert_closed()


if __name__ == "__main__":
    unittest.main()

"""Phase B direct-central actions, no offline dependencies, real temporary data."""
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openpyxl import Workbook
from position_tracking_central import CentralOperator, PositionRequest, UNCONFIRMED
from position_tracking_store import SharedEventStore
from position_tracking_worker import SingleFlightWorker


def write_personnel(path):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ΑΓΜΣ", "ΒΑΘΜΟΣ", "ΕΠΩΝΥΜΟ", "ΟΝΟΜΑ"])
    sheet.append(["999001", "TEST", "SYNTHETIC", "FIRST"])
    sheet.append(["999002", "TEST", "SYNTHETIC", "SECOND"])
    workbook.save(path)
    workbook.close()


class OperatorContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-central-operator-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / ".tde_runtime"
        self.root.mkdir()
        self.personnel = self.root / "personnel.xlsx"
        write_personnel(self.personnel)
        self.operator = CentralOperator.from_shared_directory(self.directory)
        self.start = PositionRequest("START", "999001", "1", "ΕΙΣΟΔΟΣ")

    def test_direct_start_end_and_repeated_request_are_central(self):
        result = self.operator.execute(self.start)
        self.assertEqual(result.status, "CONFIRMED")
        self.assertEqual(self.operator.execute(self.start).event["event_id"], self.start.operation_id)
        person, active = self.operator.lookup("999001")
        self.assertEqual(person.surname, "SYNTHETIC")
        self.assertEqual(active["event_id"], self.start.operation_id)
        end = PositionRequest("END", "999001", expected_start_id=active["event_id"])
        self.assertEqual(self.operator.execute(end).status, "CONFIRMED")
        self.assertEqual(self.operator.execute(end).event["event_id"], end.operation_id)
        store = SharedEventStore(self.root)
        self.assertIsNone(store.get_active("999001"))
        self.assertEqual(len(store.iter_all_events()), 2)
        self.assertEqual(len(store.search_personnel_sessions()), 1)
        self.assertEqual(list(self.directory.rglob("position_outbox.sqlite3")), [])

    def test_missing_share_never_creates_local_fallback(self):
        absent = self.directory / "absent-share"
        operator = CentralOperator(absent, self.personnel)
        result = operator.execute(self.start)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(result.message, UNCONFIRMED)
        self.assertFalse(absent.exists())

    def test_start_never_waits_for_shift_sync(self):
        with patch.object(SharedEventStore, "sync_active_shift", side_effect=AssertionError("shift coupling")) as sync:
            self.assertEqual(self.operator.execute(self.start).status, "CONFIRMED")
            sync.assert_not_called()

    def test_lost_end_ack_reads_back_original_without_replay(self):
        self.operator.execute(self.start)
        original = SharedEventStore._atomic_json
        def write(path, event):
            original(path, event)
            if path.is_relative_to(self.root / "events") and event["kind"] == "END":
                raise OSError("synthetic lost ACK")
        end = PositionRequest("END", "999001", expected_start_id=self.start.operation_id)
        with patch.object(SharedEventStore, "_atomic_json", staticmethod(write)):
            result = self.operator.execute(end)
        self.assertEqual(result.status, "CONFIRMED")
        self.assertEqual(result.event["event_id"], end.operation_id)
        self.assertEqual(len(SharedEventStore(self.root).iter_all_events()), 2)

    def test_uncertain_write_is_rechecked_without_new_operation(self):
        self.operator.execute(self.start)
        end = PositionRequest("END", "999001", expected_start_id=self.start.operation_id)
        original = SharedEventStore._atomic_json
        def write(path, event):
            original(path, event)
            if path.is_relative_to(self.root / "events") and event["kind"] == "END":
                raise OSError("synthetic lost ACK")
        with patch.object(SharedEventStore, "_atomic_json", staticmethod(write)), \
                patch.object(self.operator, "check", side_effect=OSError("host unavailable")):
            result = self.operator.execute(end)
        self.assertEqual(result.status, "UNKNOWN")
        self.assertEqual(self.operator.check(end).status, "CONFIRMED")
        store = SharedEventStore(self.root)
        self.assertEqual(len(store.iter_all_events()), 2)
        self.assertIsNone(store.get_active("999001"))

    def test_changed_windows_account_never_closes_active_start(self):
        self.operator.execute(self.start)
        with patch.dict("os.environ", {"USERNAME": "different-synthetic-user"}):
            _, active = CentralOperator.from_shared_directory(self.directory).lookup("999001")
        self.assertEqual(active["event_id"], self.start.operation_id)
        self.assertEqual(len(SharedEventStore(self.root).iter_all_events()), 1)

    def test_end_uses_actual_active_record_even_when_roster_is_unavailable(self):
        self.operator.execute(self.start)
        self.personnel.unlink()
        _, active = self.operator.lookup("999001")
        end = PositionRequest("END", "999001", expected_start_id=active["event_id"])
        self.assertEqual(self.operator.execute(end).status, "CONFIRMED")

    def test_unknown_person_cannot_start(self):
        result = self.operator.execute(replace(self.start, agms="000000"))
        self.assertEqual(result.status, "NOT_COMMITTED")
        self.assertEqual(SharedEventStore(self.root).iter_all_events(), [])

    def test_same_id_different_position_cannot_report_success(self):
        self.operator.execute(self.start)
        wrong = replace(self.start, position="2")
        self.assertEqual(self.operator.execute(wrong).status, "UNKNOWN")
        self.assertEqual(self.operator.lookup("999001")[1]["position"], "1")

    def test_stale_end_cannot_close_a_replacement(self):
        self.operator.execute(self.start)
        stale = PositionRequest("END", "999001", expected_start_id=self.start.operation_id)
        self.operator.execute(stale)
        replacement = replace(self.start, operation_id="replacement-start", when=datetime.now())
        self.operator.execute(replacement)
        rejected = self.operator.execute(replace(stale, operation_id="stale-end"))
        self.assertEqual(rejected.status, "NOT_COMMITTED")
        self.assertEqual(self.operator.lookup("999001")[1]["event_id"], replacement.operation_id)


class WorkerContract(unittest.TestCase):
    def test_one_blocked_job_cannot_be_cancelled_or_queue_more_jobs(self):
        gate = threading.Event()
        started = threading.Event()
        worker = SingleFlightWorker("TDE-test-blocked")
        def blocked():
            started.set()
            gate.wait(5)
            return "finished"
        future = worker.submit(blocked)
        self.addCleanup(gate.set)
        self.assertTrue(started.wait(1))
        self.assertFalse(future.cancel())
        for _ in range(100):
            with self.assertRaises(RuntimeError):
                worker.submit(lambda: "must never queue")
        worker.close()
        self.assertTrue(future.running())
        gate.set()
        self.assertEqual(future.result(timeout=2), "finished")
        with self.assertRaises(RuntimeError):
            worker.submit(lambda: None)


if __name__ == "__main__":
    unittest.main()

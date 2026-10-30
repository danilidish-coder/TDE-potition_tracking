"""Load on the shared folder and honest reports, on isolated synthetic data.

Field symptom (v1.2.6/v1.2.7 trial): stations froze around a user/shift change.
Cause found by code reading and measurement: every lookup, every mail poll and
every action built a NEW SharedEventStore, which creates ~20 folders, opens the
database four times and takes the GLOBAL __POSITION_TRANSACTIONS__ lock. With
15 stations over SMB that lock queued behind plain reads. These tests pin the
fixed behaviour and also that real recovery and report honesty still work.
"""
from datetime import datetime, timedelta
from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_central import CentralOperator, PositionRequest
from position_tracking_personnel import PersonnelRecord, PersonnelRepository
from position_tracking_report_text import build_shift_text
from position_tracking_settings import DEFAULT_CUTOFF
from position_tracking_store import SharedEventStore
from central_operator_regression import write_personnel


class LoadContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-load-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / ".tde_runtime"
        self.root.mkdir()
        self.personnel = self.root / "personnel.xlsx"
        write_personnel(self.personnel)
        self.operator = CentralOperator.from_shared_directory(self.directory)

    def test_many_lookups_build_one_store_and_never_take_the_global_lock(self):
        self.operator.lookup("999001")  # first use may initialise the share
        opened, made_dirs, constructed = [], [], []
        real_open, real_mkdir, real_init = os.open, Path.mkdir, SharedEventStore.__init__

        def watch_open(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                opened.append(Path(path).name)
            return real_open(path, *args, **kwargs)

        def watch_mkdir(path, *args, **kwargs):
            made_dirs.append(str(path))
            return real_mkdir(path, *args, **kwargs)

        def watch_init(store, *args, **kwargs):
            constructed.append(args)
            return real_init(store, *args, **kwargs)

        with patch("os.open", watch_open), patch.object(Path, "mkdir", watch_mkdir), \
                patch.object(SharedEventStore, "__init__", watch_init):
            for number in range(25):
                self.operator.lookup(("999001", "999002", "000000", "")[number % 4])
                self.operator.communication("station-" + str(number % 3))
        self.assertEqual(constructed, [], "a store was rebuilt for a plain read")
        self.assertEqual([name for name in opened if "__POSITION_TRANSACTIONS__" in name], [],
                         "a plain read queued on the global transaction lock")

    def test_personnel_workbook_is_parsed_once_until_it_changes(self):
        loads = []
        original = PersonnelRepository.load

        def counted(source):
            loads.append(source)
            return original(source)

        with patch.object(PersonnelRepository, "load", side_effect=counted):
            for _ in range(10):
                person, active = self.operator.lookup("999002")
                self.assertEqual(person.surname, "SYNTHETIC")
                self.assertIsNone(active)
            self.assertEqual(len(loads), 1)
            # A real central change (new person) must be seen, not cached away.
            from openpyxl import load_workbook
            workbook = load_workbook(self.personnel)
            workbook.active.append(["999003", "TEST", "SYNTHETIC", "THIRD"])
            workbook.save(self.personnel)
            workbook.close()
            person, _ = self.operator.lookup("999003")
            self.assertIsNotNone(person)
            self.assertEqual(len(loads), 2)

    def test_pending_work_is_still_recovered_by_a_lookup(self):
        start = PositionRequest("START", "999001", "1", "ΕΙΣΟΔΟΣ")
        with patch.object(SharedEventStore, "_settle_position_event", lambda self, event_id: None):
            self.assertEqual(self.operator.execute(start).status, "CONFIRMED")
        store = self.operator._store()
        unsettled = "SELECT COUNT(*) AS n FROM position_operations WHERE settled=0"
        self.assertGreater(store._position_rows(unsettled)[0]["n"], 0)
        self.assertTrue(store._position_recovery_needed())
        _, active = self.operator.lookup("999001")
        self.assertEqual(active["event_id"], start.operation_id)
        self.assertEqual(store._position_rows(unsettled)[0]["n"], 0)
        self.assertFalse(store._position_recovery_needed())

    def test_failed_first_construction_is_retried_not_cached(self):
        calls = []
        real_init = SharedEventStore.__init__

        def flaky(store, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise OSError("synthetic share outage")
            return real_init(store, *args, **kwargs)

        with patch.object(SharedEventStore, "__init__", flaky):
            with self.assertRaises(OSError):
                self.operator.lookup("999001")
            person, _ = self.operator.lookup("999001")
        self.assertIsNotNone(person)
        self.assertEqual(len(calls), 2)

    def test_two_threads_share_one_store(self):
        built = []
        real_init = SharedEventStore.__init__

        def counted(store, *args, **kwargs):
            built.append(1)
            return real_init(store, *args, **kwargs)

        errors = []

        def reader():
            try:
                self.operator.lookup("999001")
            except Exception as error:  # pragma: no cover - failure detail
                errors.append(error)

        with patch.object(SharedEventStore, "__init__", counted):
            threads = [threading.Thread(target=reader) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(20)
        self.assertEqual(errors, [])
        self.assertEqual(len(built), 1)


class ReportHonesty(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tde-report-warning-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".tde_runtime"
        self.root.mkdir()
        self.store = SharedEventStore(self.root)
        self.person = PersonnelRecord("999001", "TEST", "SYNTHETIC", "FIRST")
        # Fixed date inside the 10:00-10:00 report window, independent of the clock.
        self.day = datetime(2026, 1, 15, 11, 0)
        self.store.start(self.person, "1", "ΕΙΣΟΔΟΣ", when=self.day)
        self.store.end(self.person, when=self.day + timedelta(minutes=30))
        folder = next(self.store.events.rglob("*.json")).parent
        self.folder = folder

    def report(self):
        return build_shift_text(self.store, self.day.date(), DEFAULT_CUTOFF)

    def test_clean_share_gives_no_warning(self):
        self.assertNotIn("ΠΡΟΣΟΧΗ", self.report())
        self.assertEqual(self.store.read_problems(), [])

    def test_unreadable_registration_is_reported_not_hidden(self):
        (self.folder / "broken.json").write_text('{"kind": "START", "event_', encoding="utf-8")
        text = self.report()
        self.assertIn("ΠΡΟΣΟΧΗ: 1 αρχεία καταχώρισης ΔΕΝ διαβάστηκαν", text)
        self.assertIn("ΕΛΛΙΠΗΣ", text)
        self.assertEqual(len(self.store.read_problems()), 1)
        # The readable registrations are still reported.
        self.assertIn("SYNTHETIC", text)

    def test_readable_json_that_is_not_an_event_is_not_a_lost_registration(self):
        (self.folder / "note.json").write_text('{"remark": "not an event"}', encoding="utf-8")
        self.assertNotIn("ΠΡΟΣΟΧΗ", self.report())

    def test_next_report_forgets_the_previous_problem(self):
        broken = self.folder / "broken.json"
        broken.write_text("{", encoding="utf-8")
        self.assertIn("ΠΡΟΣΟΧΗ", self.report())
        broken.unlink()
        self.assertNotIn("ΠΡΟΣΟΧΗ", self.report())

    def test_problems_are_per_thread(self):
        (self.folder / "broken.json").write_text("{", encoding="utf-8")
        seen = {}

        def other():
            seen["notice"] = self.report()

        thread = threading.Thread(target=other)
        thread.start()
        thread.join(20)
        self.assertIn("ΠΡΟΣΟΧΗ", seen["notice"])
        # This thread never read events, so it must not inherit that thread's problem.
        self.store.clear_read_problems()
        self.assertEqual(self.store.read_problems(), [])


if __name__ == "__main__":
    unittest.main()

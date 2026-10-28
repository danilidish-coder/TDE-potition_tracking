"""Phase D3A: synthetic central completed work is immutable and never LIVE."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord


class HistoricalWorkStageA(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="tde-historical-synthetic-")
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name) / ".tde_runtime"
        root.mkdir()
        self.store = SharedEventStore(root)
        self.base = (datetime.now()-timedelta(hours=2)).replace(microsecond=0)
        self.shift_id = "synthetic-shift-" + uuid.uuid4().hex
        self.store._store_shift_snapshot(dict(
            shift_id=self.shift_id, version=2, status="FINALIZED",
            start_at=(self.base-timedelta(hours=1)).isoformat(),
            end_at=(self.base+timedelta(hours=1)).isoformat(),
            approved=["999001"], excluded=[], pending=[]))
        self.person = PersonnelRecord("999002", "TEST", "HISTORY", "ONLY")

    def intent(self, action_id=None):
        action_id = action_id or uuid.uuid4().hex
        return dict(action_id=action_id, action="HISTORICAL_ADD",
                    reason="Missing completed work", identity="DECLARED_NOT_AUTHENTICATED",
                    declared_officer=dict(agms="999001",full_name="TEST OFFICER"),
                    recorded_at=datetime.now().isoformat(),
                    intent=dict(action="HISTORICAL_ADD",values=dict(shift_id=self.shift_id,agms=self.person.agms)))

    def add(self, **changes):
        values = dict(shift_id=self.shift_id,person=self.person,position="1",direction="ΕΙΣΟΔΟΣ",
                      start_at=self.base,end_at=self.base+timedelta(minutes=20),
                      reason="Missing completed work",intent=self.intent())
        values.update(changes)
        return self.store.add_historical_completed(**values)

    def test_accepted_completed_row_and_receipt_survive_reopening_without_live_change(self):
        before_active = self.store.active_all()
        before_events = list(self.store.events.rglob("*.json"))
        before_ops = self.store._position_rows("SELECT * FROM position_operations")
        receipt = self.add()
        self.assertEqual(receipt["after"]["agms"],"999002")
        self.assertEqual(self.store.officer_action(receipt["action_id"]),receipt)
        self.assertEqual(self.store.active_all(),before_active)
        self.assertEqual(list(self.store.events.rglob("*.json")),before_events)
        self.assertEqual(self.store._position_rows("SELECT * FROM position_operations"),before_ops)
        new = SharedEventStore(self.store.root)
        self.assertEqual(len(new.historical_for_shift(self.shift_id)),1)
        self.assertEqual(new.historical_for_shift(self.shift_id)[0]["action_id"],receipt["action_id"])
        with new._shift_db_connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM historical_work")

    def test_identical_request_is_idempotent_and_conflicting_id_is_rejected(self):
        request = self.intent()
        first = self.add(intent=request)
        self.assertEqual(self.add(intent=request),first)
        self.assertEqual(len(self.store.historical_for_shift(self.shift_id)),1)
        other = {**request, "intent":dict(action="HISTORICAL_ADD",values=dict(agms="DIFFERENT"))}
        with self.assertRaisesRegex(Exception,"διαφορετική"):
            self.add(intent=other)
        self.assertEqual(len(self.store.historical_for_shift(self.shift_id)),1)

    def test_invalid_clock_or_shift_does_not_write(self):
        with self.assertRaises(ValueError):
            self.add(end_at=self.base)
        with self.assertRaises(ValueError):
            self.add(shift_id="missing")
        self.assertFalse(self.store.historical_for_shift(self.shift_id))

    def test_overlap_same_person_or_booth_rejected_but_distinct_work_allowed(self):
        self.add()
        with self.assertRaisesRegex(ValueError,"ΑΓΜΣ"):
            self.add(position="2")
        with self.assertRaisesRegex(ValueError,"θέση"):
            self.add(person=PersonnelRecord("999003","TEST","OTHER","PERSON"))
        distinct = self.add(person=PersonnelRecord("999003","TEST","OTHER","PERSON"),
                            position="2",start_at=self.base+timedelta(minutes=21),
                            end_at=self.base+timedelta(minutes=30))
        self.assertEqual(len(self.store.historical_for_shift(self.shift_id)),2)
        self.assertEqual(distinct["after"]["position"],"2")

    def test_concurrent_same_booth_accepts_exactly_one(self):
        def attempt(index):
            try:
                return self.add(person=PersonnelRecord(str(999010+index),"TEST","WORKER",str(index)))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts = list(pool.map(attempt, range(4)))
        self.assertEqual(sum(x is not None for x in receipts),1)
        self.assertEqual(len(self.store.historical_for_shift(self.shift_id)),1)


if __name__=="__main__":
    unittest.main()

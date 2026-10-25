"""Focused v1.2.6 regression reproductions; synthetic temporary SQLite only.

Run: python -m unittest discover -s tests -p 'test_offline_freeze_scenarios.py' -v
No operational records or shared paths are used.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_offline import OfflineJournal, OfflineConflict


def officer(agms):
    return SimpleNamespace(agms=agms, rank="ΑΣΤ", surname="TEST", given_name="TEST")


class FakeStore:
    def __init__(self):
        self.active = {}
        self.counter = 0
    def start(self, person, position, direction, **kw):
        self.counter += 1
        if person.agms in self.active:
            raise ValueError("Officer already active centrally")
        if any(x["position"] == position for x in self.active.values()):
            raise ValueError("Booth already occupied centrally")
        event = {"event_id": kw["event_id"], "position": position,
                 "direction": direction, "agms": person.agms, "timestamp": kw["when"].isoformat()}
        self.active[person.agms] = event
        return event
    def end(self, person, **kw):
        self.counter += 1
        cur = self.active.get(person.agms)
        if not cur or cur["event_id"] != kw["expected_start_event_id"]:
            raise ValueError("START changed or no central active")
        self.active.pop(person.agms)
        return {"event_id": kw["event_id"], "kind": "END", "agms": person.agms}


class OfflineFreezeScenarios(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.j = OfflineJournal(Path(self.t.name) / "queue")
        self.store = FakeStore()

    def test_supervisor_central_start_then_booth_offline_start_blocks_all(self):
        # AΞΥΠ centrally starts officer 111 on position 5.
        self.store.start(officer("111"), "5", "ΕΙΣΟΔΟΣ", event_id="central-111",
                         when=__import__("datetime").datetime.now())
        # Booth's local view is stale; it adds same officer/booth as offline START.
        self.j.enqueue("START", officer("111"), "5", "ΕΙΣΟΔΟΣ")
        result = self.j.sync(self.store, SimpleNamespace)
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["pending"], 1)
        # The affected officer/booth is guarded, but other officers can work.
        with self.assertRaises(OfflineConflict):
            self.j.enqueue("START", officer("111"), "6", "ΕΞΟΔΟΣ")
        with self.assertRaises(OfflineConflict):
            self.j.enqueue("START", officer("222"), "5", "ΕΞΟΔΟΣ")
        other = self.j.enqueue("START", officer("222"), "6", "ΕΞΟΔΟΣ")
        result = self.j.sync(self.store, SimpleNamespace)
        self.assertIn(other["operation_id"], result["applied"])
        self.assertIn("222", self.store.active)
        self.assertEqual(len(result["conflicts"]), 1)

    def test_rejection_can_expose_next_conflict_and_refreeze(self):
        for agms, position in (("111", "5"), ("222", "6")):
            self.store.start(officer(agms), position, "ΕΙΣΟΔΟΣ",
                             event_id="central-"+agms,
                             when=__import__("datetime").datetime.now())
            self.j.enqueue("START", officer(agms), position, "ΕΙΣΟΔΟΣ")
        self.assertEqual(len(self.j.sync(self.store, SimpleNamespace)["conflicts"]), 1)
        first = self.j.conflicts()[0]["id"]
        self.j.resolve_conflict(first, "999", "Επιβεβαιώθηκε στο κέντρο")
        # An unrelated pending conflict can be found and retained independently.
        self.assertEqual(len(self.j.sync(self.store, SimpleNamespace)["conflicts"]), 1)
        self.assertNotEqual(self.j.conflicts()[0]["id"], first)

    def test_network_error_stays_pending_not_false_success(self):
        self.j.enqueue("START", officer("333"), "5", "ΕΙΣΟΔΟΣ")
        class Down:
            def start(self, *args, **kwargs):
                raise OSError("Network unavailable")
        result = self.j.sync(Down(), SimpleNamespace)
        self.assertEqual(result["applied"], [])
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["conflicts"], [])

if __name__ == "__main__":
    unittest.main()

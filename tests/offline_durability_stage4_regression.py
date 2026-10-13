"""Stage 4: durable offline-journal invariants, isolated from production data."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_offline import OfflineJournal


class Person:
    def __init__(self, agms="901", rank="Α/Φ", surname="TEST", given_name="USER"):
        self.agms = agms
        self.rank = rank
        self.surname = surname
        self.given_name = given_name


class IntermittentStore:
    def __init__(self):
        self.events = []
        self.fail = True

    def start(self, person, position, direction, **kwargs):
        if self.fail:
            raise OSError("SMB disconnected")
        self.events.append(("START", kwargs["event_id"], kwargs["when"]))
        return {"event_id": kwargs["event_id"], "position": position,
                "direction": direction, "agms": person.agms}

    def end(self, person, **kwargs):
        if self.fail:
            raise OSError("SMB disconnected")
        self.events.append(("END", kwargs["event_id"], kwargs["when"]))
        return {"event_id": kwargs["event_id"]}


class OfflineDurabilityStage4(unittest.TestCase):
    def test_pending_survives_restart_and_replays_original_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            j = OfflineJournal(folder)
            person = Person()
            start = j.enqueue("START", person, "ΓΚΙΣΕ 1", "ΕΞΟΔΟΣ", "client-a")
            end = j.enqueue("END", person, client_id="client-a")
            recorded = [(op["id"], op["created_at"], op["kind"])
                        for op in j._rows(("PENDING",))]
            self.assertEqual([x[2] for x in recorded], ["START", "END"])
            self.assertEqual([x[0] for x in recorded],
                             [start["operation_id"], end["operation_id"]])
            self.assertEqual(j.pending_count(), 2)
            store = IntermittentStore()
            interrupted = j.sync(store, Person)
            self.assertEqual(interrupted["applied"], [])
            self.assertEqual(interrupted["pending"], 2)
            del j
            restarted = OfflineJournal(folder)
            self.assertEqual(restarted.pending_count(), 2)
            store.fail = False
            result = restarted.sync(store, Person)
            self.assertEqual(result["pending"], 0)
            self.assertEqual(result["conflicts"], [])
            self.assertEqual([(k, ident) for k, ident, _ in store.events],
                             [("START", start["operation_id"]),
                              ("END", end["operation_id"])])
            self.assertEqual([dt.isoformat(timespec="seconds") for _, _, dt in store.events],
                             [created for _, created, _ in recorded])
            self.assertEqual(restarted.sync(store, Person)["applied"], [])
            self.assertEqual(len(store.events), 2)

    def test_legacy_conflict_is_not_silently_deleted_on_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            j = OfflineJournal(folder)
            op = j.enqueue("START", Person(), "ΓΚΙΣΕ 2", "ΕΞΟΔΟΣ")
            j._mark(op["operation_id"], "CONFLICT", "manual review required")
            del j
            restarted = OfflineJournal(folder)
            self.assertEqual(restarted.pending_count(), 1)
            self.assertEqual(restarted.conflicts()[0]["id"], op["operation_id"])
            with self.assertRaises(Exception):
                restarted.enqueue("START", Person("902"), "ΓΚΙΣΕ 3", "ΕΞΟΔΟΣ")


if __name__ == "__main__":
    unittest.main()

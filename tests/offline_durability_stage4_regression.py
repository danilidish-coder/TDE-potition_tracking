"""Stage 4: durable offline-journal invariants, isolated from production data."""
import sys
import threading
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

    def test_simultaneous_offline_claims_same_booth_allow_only_one(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = OfflineJournal(folder)
            barrier = threading.Barrier(2)
            results = []
            lock = threading.Lock()

            def claim(person):
                barrier.wait()
                try:
                    outcome = ("accepted", journal.enqueue(
                        "START", person, "ΓΚΙΣΕ 7", "ΕΞΟΔΟΣ")["operation_id"])
                except ValueError as exc:
                    outcome = ("rejected", str(exc))
                with lock:
                    results.append(outcome)

            workers = [threading.Thread(target=claim, args=(Person(str(900 + i)),))
                       for i in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=8)
                self.assertFalse(worker.is_alive(), "Offline claim deadlocked")
            self.assertEqual(sorted(item[0] for item in results),
                             ["accepted", "rejected"])
            self.assertEqual(len(journal._rows(("PENDING",))), 1)

    def test_restart_after_server_commit_before_local_ack_replays_same_id(self):
        """A lost acknowledgement must not create a second central START."""
        with tempfile.TemporaryDirectory() as folder:
            journal = OfflineJournal(folder)
            op = journal.enqueue("START", Person(), "ΓΚΙΣΕ 8", "ΕΞΟΔΟΣ")
            class AckLostStore:
                def __init__(self):
                    self.events = {}
                    self.calls = 0
                def start(self, person, position, direction, **kwargs):
                    self.calls += 1
                    ident = kwargs["event_id"]
                    self.events.setdefault(ident, kwargs["when"])
                    if self.calls == 1:
                        raise OSError("connection lost after central commit")
                    return {"event_id": ident, "position": position,
                            "direction": direction, "agms": person.agms}
                def end(self, person, **kwargs):
                    raise AssertionError("Unexpected END")
            store = AckLostStore()
            self.assertEqual(journal.sync(store, Person)["pending"], 1)
            self.assertEqual(len(store.events), 1)
            restarted = OfflineJournal(folder)
            self.assertEqual(restarted.sync(store, Person)["pending"], 0)
            self.assertEqual(len(store.events), 1)
            self.assertEqual(list(store.events), [op["operation_id"]])
            self.assertEqual(store.calls, 2)

    def test_restart_after_end_commit_before_local_ack_keeps_single_end(self):
        """A lost END acknowledgement must replay the same central END ID."""
        with tempfile.TemporaryDirectory() as folder:
            journal = OfflineJournal(folder)
            person = Person()

            class AckLostOnEndStore:
                def __init__(self):
                    self.events = {}
                    self.end_calls = 0

                def start(self, person, position, direction, **kwargs):
                    ident = kwargs["event_id"]
                    self.events.setdefault(ident, "START")
                    return {"event_id": ident, "position": position,
                            "direction": direction, "agms": person.agms}

                def end(self, person, **kwargs):
                    self.end_calls += 1
                    ident = kwargs["event_id"]
                    self.events.setdefault(ident, "END")
                    if self.end_calls == 1:
                        raise OSError("connection lost after central END commit")
                    return {"event_id": ident}

            store = AckLostOnEndStore()
            start = journal.enqueue("START", person, "ΓΚΙΣΕ 9", "ΕΞΟΔΟΣ")
            self.assertEqual(journal.sync(store, Person)["pending"], 0)
            end = journal.enqueue("END", person)
            self.assertEqual(journal.sync(store, Person)["pending"], 1)
            expected = {start["operation_id"]: "START",
                        end["operation_id"]: "END"}
            self.assertEqual(store.events, expected)

            restarted = OfflineJournal(folder)
            self.assertEqual(restarted.sync(store, Person)["pending"], 0)
            self.assertEqual(store.events, expected)
            self.assertEqual(store.end_calls, 2)
            self.assertIsNone(restarted.local_active(person.agms))

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

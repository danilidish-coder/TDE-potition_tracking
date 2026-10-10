"""Field regression: late Windows handoff after old officer moved elsewhere,
previous v1.2.5 stuck conflicts, and unrelated officers must still sync.
"""
import importlib.util
import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def person(n):
    return MOD.PersonnelRecord(str(n), "ΑΣΤ", "SURNAME" + str(n), "NAME")


with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    store = MOD.SharedEventStore(root / "TDE_DATA")
    journal = MOD.OfflineJournal(root / "machine_queue")
    a, b, third = person(90001), person(90002), person(90003)
    hostname = MOD.socket.gethostname
    original_user = os.environ.get("USERNAME")
    try:
        MOD.socket.gethostname = lambda: "EXIT-08"
        os.environ["USERNAME"] = "USER_A"
        old_start = journal.enqueue("START", a, "8", "ΕΞΟΔΟΣ", "APP_A")
        assert journal.sync(store, MOD.PersonnelRecord)["pending"] == 0
        assert store.get_active(a.agms)["event_id"] == old_start["operation_id"]

        os.environ["USERNAME"] = "USER_B"
        # Windows B starts while previous person's locally observed START exists.
        closed = journal.auto_close_previous_windows_users("EXIT-08", "USER_B")
        assert len(closed) == 1
        assert journal.local_active(a.agms) is None

        # On a different machine the officer's old shift is closed and
        # officer A starts at a new workstation before EXIT-08 reconnects.
        store.end(a)
        replacement = store.start(a, "12", "ΕΞΟΔΟΣ")
        start_b = journal.enqueue("START", b, "8", "ΕΞΟΔΟΣ", "APP_B")

        # Emulate v1.2.5, which turned delayed END into CONFLICT and blocked ALL.
        orphan = next(x for x in journal._rows() if x["kind"] == "END")
        journal._mark(orphan["id"], "CONFLICT", "Η θέση άλλαξε χρήστη πριν επιβεβαιωθεί η λήξη")
        assert len(journal.conflicts()) == 1

        recovered = journal.sync(store, MOD.PersonnelRecord)
        assert recovered["conflicts"] == [], recovered
        assert recovered["pending"] == 0, recovered
        assert store.get_active(a.agms)["event_id"] == replacement["event_id"]
        assert store.get_active(b.agms)["event_id"] == start_b["operation_id"]
        assert not journal.conflicts()
        assert journal.sync(store, MOD.PersonnelRecord)["applied"] == []
        assert any(x.get("action") == "OFFLINE_HANDOFF_END_ALREADY_SUPERSEDED"
                   for x in store.iter_admin_audit()) if hasattr(store, "iter_admin_audit") else True

        # Unrelated conflict cannot stop newly started officer at a different booth.
        bad = journal.enqueue("START", third, "9", "ΕΞΟΔΟΣ", "APP_C")
        journal._mark(bad["operation_id"], "CONFLICT", "test")
        assert journal.conflicts()
        other = person(90004)
        good = journal.enqueue("START", other, "10", "ΕΞΟΔΟΣ", "APP_D")
        report = journal.sync(store, MOD.PersonnelRecord)
        assert report["conflicts"], report
        assert store.get_active(other.agms)["event_id"] == good["operation_id"]
        assert store.get_active(a.agms)["event_id"] == replacement["event_id"]
        try:
            journal.enqueue("END", third)
        except MOD.OfflineConflict:
            pass
        else:
            raise AssertionError("Unsafe END of conflicted personnel accepted")
    finally:
        MOD.socket.gethostname = hostname
        if original_user is None:
            os.environ.pop("USERNAME", None)
        else:
            os.environ["USERNAME"] = original_user

print("FIELD_HANDOFF_CONFLICT_RECOVERY: PASS")

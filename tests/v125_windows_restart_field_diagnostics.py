"""Diagnostics on EXACT v1.2.5, no production-source modifications.

Models Windows sign-out/restart as process termination and opening the same
machine-persistent SQLite outbox. This is NOT a real physical Windows reboot.
Reproduce yesterday's stale rejected handoff, AXYP rejection, next login and
reboot, alongside normal non-failing cases. Expected historical bugs are
ASSERTED as observed facts, not confused with corrected behavior.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src" / "position_tracking.py").read_text(encoding="utf-8")
assert 'APP_VERSION = "1.2.5"' in SOURCE, "WRONG VERSION: must test actual v1.2.5"
spec = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
pt = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pt
spec.loader.exec_module(pt)

hostname_original = pt.socket.gethostname
username_original = os.environ.get("USERNAME")
completed = []

def person(n):
    return pt.PersonnelRecord(str(n), "AST", "OFFICER" + str(n), "TEST")

def setup(root, host):
    pt.socket.gethostname = lambda host=host: host
    return pt.SharedEventStore(root / "central" / "TDE_DATA"), pt.OfflineJournal(root / host / "machine_journal")

def log(title):
    completed.append(title)
    print("DIAGNOSTIC PASS:", title, flush=True)

def start_sync(journal, store, officer, position, user, host):
    os.environ["USERNAME"] = user
    pt.socket.gethostname = lambda host=host: host
    op = journal.enqueue("START", officer, position, "ΕΞΟΔΟΣ", user + "_CLIENT")
    result = journal.sync(store, pt.PersonnelRecord)
    assert result["pending"] == 0 and not result["conflicts"], result
    assert store.get_active(officer.agms)["event_id"] == op["operation_id"]
    return op

def close_and_reopen(root, host):
    # The app/process has ended; the central share and local persistent DB survive.
    return pt.OfflineJournal(root / host / "machine_journal")

try:
    # 1: Officer presses END and it is centrally ACKed; no real app EXIT required.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-08"
        store, journal = setup(root, host)
        a, b = person(8101), person(8102)
        start_sync(journal, store, a, "8", "USER_A", host)
        journal.enqueue("END", a, client_id="USER_A_CLIENT")
        assert journal.sync(store, pt.PersonnelRecord)["pending"] == 0
        assert store.get_active(a.agms) is None
        journal = close_and_reopen(root, host)
        os.environ["USERNAME"] = "USER_B"
        assert journal.auto_close_previous_windows_users(host, "USER_B") == []
        start_sync(journal, store, b, "8", "USER_B", host)
        log("01_END_ACK_NO_PROGRAM_EXIT_NEW_OFFICER_CAN_START")

    # 2: USER_A signs out without END. B's handoff queues END, sync succeeds.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-09"
        store, journal = setup(root, host)
        a, b = person(8201), person(8202)
        start_sync(journal, store, a, "9", "USER_A", host)
        journal = close_and_reopen(root, host)
        os.environ["USERNAME"] = "USER_B"
        ids = journal.auto_close_previous_windows_users(host, "USER_B")
        assert len(ids) == 1
        result = journal.sync(store, pt.PersonnelRecord)
        assert not result["conflicts"] and result["pending"] == 0, result
        assert store.get_active(a.agms) is None
        start_sync(journal, store, b, "9", "USER_B", host)
        log("02_SIGNOUT_WITHOUT_END_NORMAL_HANDOFF")

    # 3: Restart with SAME Windows user does not by itself write END centrally.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-10"
        store, journal = setup(root, host)
        a = person(8301)
        start_sync(journal, store, a, "10", "USER_A", host)
        before = store.get_active(a.agms)["event_id"]
        journal = close_and_reopen(root, host)
        assert journal.auto_close_previous_windows_users(host, "USER_A") == []
        assert store.get_active(a.agms)["event_id"] == before
        assert journal.local_active(a.agms)["event_id"] == before
        log("03_RESTART_SAME_USER_DOES_NOT_CLEAR_CENTRAL_ACTIVE")

    # 4: Lost network after END: pending END survives app/reboot, later replays.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-11"
        store, journal = setup(root, host)
        a, b = person(8401), person(8402)
        start_sync(journal, store, a, "11", "USER_A", host)
        journal.enqueue("END", a, client_id="USER_A_CLIENT")
        assert store.get_active(a.agms) is not None  # no central ACK yet
        journal = close_and_reopen(root, host)
        os.environ["USERNAME"] = "USER_B"
        assert journal.auto_close_previous_windows_users(host, "USER_B") == []
        assert journal.local_active(a.agms) is None
        result = journal.sync(store, pt.PersonnelRecord)
        assert result["pending"] == 0 and not result["conflicts"], result
        assert store.get_active(a.agms) is None
        start_sync(journal, store, b, "11", "USER_B", host)
        log("04_PENDING_END_PERSISTS_AND_RECOVERS_AFTER_RESTART")

    # 5: Central safely closes last Windows user even after local process exits.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-12"
        store, journal = setup(root, host)
        a = person(8501)
        start_sync(journal, store, a, "12", "OLD_USER", host)
        journal = close_and_reopen(root, host)
        closed = store.close_previous_windows_user_positions(host, "NEW_USER")
        assert len(closed) == 1 and closed[0]["agms"] == a.agms
        assert store.get_active(a.agms) is None
        assert store.close_previous_windows_user_positions(host, "NEW_USER") == []
        log("05_CENTRAL_WINDOWS_HANDOFF_IDEMPOTENT")

    # 6: Actual observed incident. A ended/moved at central but EXIT PC retains
    # A's old observed START. B's auto END targets OLD start id => CONFLICT.
    # AXYP rejects; C logs in after full process restart => same A reappears.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-08"
        store, journal = setup(root, host)
        a, b = person(8601), person(8602)
        old = start_sync(journal, store, a, "8", "OLD_USER", host)
        store.end(a)
        moved = store.start(a, "13", "ΕΞΟΔΟΣ", origin_computer="EXIT-13", origin_user="OLD_USER")
        assert moved["event_id"] != old["operation_id"]
        assert journal.local_active(a.agms)["event_id"] == old["operation_id"]
        os.environ["USERNAME"] = "NEW_USER_B"
        first = journal.auto_close_previous_windows_users(host, "NEW_USER_B")
        assert len(first) == 1
        r = journal.sync(store, pt.PersonnelRecord)
        assert len(r["conflicts"]) == 1, r
        try:
            journal.enqueue("START", b, "8", "ΕΞΟΔΟΣ", "NEW_CLIENT")
            raise AssertionError("Expected global CONFLICT block")
        except pt.OfflineConflict:
            pass
        journal.resolve_conflict(first[0], "AXYP_01", "Checked old END against central active")
        assert not journal.conflicts()
        assert journal.local_active(a.agms)["event_id"] == old["operation_id"]

        # Actual child Python process verifies SQLite persists across process exit.
        check = subprocess.run(
            [sys.executable, "-c",
             "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); "
             "print(db.execute('select count(*) from observed').fetchone()[0]); "
             "print(db.execute(\"select count(*) from operations where status='REJECTED'\").fetchone()[0])",
             str(journal.path)],
            capture_output=True, text=True, check=True,
        )
        assert [int(x) for x in check.stdout.split()] == [1, 1], check.stdout
        log("06_AXYP_REJECTION_LEAVES_STALE_CACHE_IN_PERSISTENT_SQLITE")

        # Simulated Windows restart: reconstruct app and local journal from
        # the exact same on-disk data, preserving the unchanged central share.
        for number, user in enumerate(("NEW_USER_C", "NEW_USER_D", "NEW_USER_E"), 1):
            journal = close_and_reopen(root, host)
            os.environ["USERNAME"] = user
            assert journal.local_active(a.agms)["event_id"] == old["operation_id"]
            generated = journal.auto_close_previous_windows_users(host, user)
            assert len(generated) == 1, (number, generated)
            r = journal.sync(store, pt.PersonnelRecord)
            assert len(r["conflicts"]) == 1, r
            assert store.get_active(a.agms)["event_id"] == moved["event_id"]
            journal.resolve_conflict(generated[0], "AXYP_01", "Reviewed stale handoff after Windows login")
            assert not journal.conflicts()
        log("07_RESTART_DOES_NOT_PREVENT_REPEATED_SAME_OLD_AGMS_IN_V125")

    # 8: The officer only pressed END centrally (did not move): stale local
    # observed record can still generate an invalid automatic END.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-09"
        store, journal = setup(root, host)
        a = person(8801)
        old = start_sync(journal, store, a, "9", "OLD_USER", host)
        store.end(a)
        assert store.get_active(a.agms) is None
        os.environ["USERNAME"] = "NEW_USER_B"
        ids = journal.auto_close_previous_windows_users(host, "NEW_USER_B")
        assert len(ids) == 1
        assert len(journal.sync(store, pt.PersonnelRecord)["conflicts"]) == 1
        journal.resolve_conflict(ids[0], "AXYP_01", "Central END confirmed by duty officer")
        journal = close_and_reopen(root, host)
        assert journal.auto_close_previous_windows_users(host, "NEW_USER_C")
        log("08_CENTRAL_END_BUT_STALE_CACHE_REGENERATES_HANDOFF")

    # 9: Conflict persists across restart even before AXYP handles it.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-10"
        store, journal = setup(root, host)
        a, b = person(8901), person(8902)
        start_sync(journal, store, a, "10", "OLD_USER", host)
        store.end(a)
        os.environ["USERNAME"] = "NEW_USER"
        journal.auto_close_previous_windows_users(host, "NEW_USER")
        assert journal.sync(store, pt.PersonnelRecord)["conflicts"]
        journal = close_and_reopen(root, host)
        assert len(journal.conflicts()) == 1
        try:
            journal.enqueue("START", b, "10", "ΕΞΟΔΟΣ", "NEW_CLIENT")
            raise AssertionError("Conflict unexpectedly cleared by reboot")
        except pt.OfflineConflict:
            pass
        log("09_UNRESOLVED_CONFLICT_SURVIVES_RESTART_AND_BLOCKS_NEW_START")

    # 10: Same machine CANNOT use different Windows login to clear stale DB,
    # while a separate machine's independent outbox can still START.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); host = "EXIT-11"
        store, journal = setup(root, host)
        a, b = person(9001), person(9002)
        start_sync(journal, store, a, "11", "OLD_USER", host)
        store.end(a)
        os.environ["USERNAME"] = "NEW_USER"
        journal.auto_close_previous_windows_users(host, "NEW_USER")
        assert journal.sync(store, pt.PersonnelRecord)["conflicts"]
        other = pt.OfflineJournal(root / "EXIT-14" / "machine_journal")
        pt.socket.gethostname = lambda: "EXIT-14"
        start_sync(other, store, b, "14", "OTHER_USER", "EXIT-14")
        assert store.get_active(b.agms) is not None
        assert journal.conflicts()
        log("10_SINGLE_PC_LOCAL_CONFLICT_OTHER_PC_CONTINUES")

    print("V125_RESTART_DIAGNOSTICS_DONE: 10 SCENARIOS", flush=True)
    print("OBSERVATION: v1.2.5 sometimes has persistent local stale observed cache.", flush=True)
    print("OBSERVATION: recreating app after restart does NOT itself repair rejected local handoff.", flush=True)
    print("NOTE: Process restart is an OS reboot model, not physical power cycling.", flush=True)
finally:
    pt.socket.gethostname = hostname_original
    if username_original is None:
        os.environ.pop("USERNAME", None)
    else:
        os.environ["USERNAME"] = username_original

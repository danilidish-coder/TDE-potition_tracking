"""Field reproduction: stale old officer reappears after every Windows login.

Two EXIT booths; previous officer moved to another station; handoff auto-END
was rejected by AXYP, which must NOT trigger a new END or block the next
user on each login. No false END, no loss of history, and no altered new START.
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def officer(n):
    return MOD.PersonnelRecord(str(n), "AST", "SURNAME" + str(n), "FIRST")


hostname = MOD.socket.gethostname
old_username = os.environ.get("USERNAME")
try:
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        store = MOD.SharedEventStore(base / "shared" / "TDE_DATA")
        for i, booth in enumerate((8, 9)):
            host = f"EXIT-{booth}"
            old = officer(98001 + i)
            newcomer = officer(98101 + i)
            journal_path = base / host / "machine_queue"
            journal = MOD.OfflineJournal(journal_path)
            MOD.socket.gethostname = lambda host=host: host
            os.environ["USERNAME"] = "OLD_ACCOUNT"

            old_start = journal.enqueue("START", old, str(booth), "ΕΞΟΔΟΣ", "OLD_CLIENT")
            assert journal.sync(store, MOD.PersonnelRecord)["pending"] == 0
            assert journal.local_active(old.agms)["event_id"] == old_start["operation_id"]

            # Old officer legitimately moves, has NEW active start elsewhere.
            store.end(old)
            replacement = store.start(
                old, str(booth + 4), "ΕΞΟΔΟΣ",
                origin_computer=f"EXIT-{booth + 4}", origin_user="OLD_ACCOUNT",
            )

            # User 2 logs on; stale auto-END becomes a conflict and AXYP rejects.
            os.environ["USERNAME"] = "NEW_ACCOUNT_1"
            original_handoffs = journal.auto_close_previous_windows_users(host, "NEW_ACCOUNT_1")
            assert len(original_handoffs) == 1, original_handoffs
            handoff_id = original_handoffs[0]
            journal._mark(handoff_id, "CONFLICT", "Old session superseded")
            journal.resolve_conflict(handoff_id, "OFFICER_AXYP", "Verified: officer moved to another booth")
            assert journal.conflicts() == [], journal.conflicts()

            # This is the reported incident: old cached START still appears in
            # observed, despite the AXYP already resolving the conflict.
            assert journal.local_active(old.agms)["event_id"] == old_start["operation_id"]
            for account in ("NEW_ACCOUNT_2", "NEW_ACCOUNT_3", "NEW_ACCOUNT_4"):
                os.environ["USERNAME"] = account
                # Recreate the application/local journal, like Windows login.
                journal = MOD.OfflineJournal(journal_path)
                assert journal.auto_close_previous_windows_users(host, account) == [], account
                assert journal.conflicts() == [], account

            # Recovery sync verifies the central ID and retires old local cache,
            # while preserving the officer's newer active position.
            result = journal.sync(store, MOD.PersonnelRecord)
            assert not result["conflicts"] and result["pending"] == 0, result
            actual = journal.local_active(old.agms)
            assert actual and actual["event_id"] == replacement["event_id"], actual
            assert actual["computer"] == f"EXIT-{booth + 4}", actual
            assert store.get_active(old.agms)["event_id"] == replacement["event_id"]
            audit = store.audit / "offline_handoff_reconciliations" / (handoff_id + "_rejected_cache.json")
            assert audit.is_file(), audit
            note = json.loads(audit.read_text(encoding="utf-8"))
            assert note["old_start_event_id"] == old_start["operation_id"]
            assert note["current_start_event_id"] == replacement["event_id"]

            # The new officer is allowed to work the now-free original booth.
            os.environ["USERNAME"] = "NEW_ACCOUNT_4"
            new_start = journal.enqueue("START", newcomer, str(booth), "ΕΞΟΔΟΣ", "NEW_CLIENT")
            result = journal.sync(store, MOD.PersonnelRecord)
            assert not result["conflicts"] and result["pending"] == 0, result
            assert store.get_active(newcomer.agms)["event_id"] == new_start["operation_id"]
            assert store.get_active(old.agms)["event_id"] == replacement["event_id"]

            # Repeat with yet another user; no old END regenerated.
            os.environ["USERNAME"] = "NEW_ACCOUNT_5"
            assert journal.auto_close_previous_windows_users(host, "NEW_ACCOUNT_5")
            # This END belongs to CURRENT new officer on the old booth; the
            # other, moved officer must never get an additional automatic END.
            historical = [
                rec for rec in journal._rows(("PENDING", "CONFLICT", "REJECTED", "RECONCILED", "APPLIED"))
                if rec["agms"] == old.agms and rec["kind"] == "END"
                and json.loads(rec["payload"]).get("reason") == "WINDOWS_USER_HANDOFF_OFFLINE"
            ]
            assert len(historical) == 1, historical
            assert historical[0]["status"] == "REJECTED", historical
            assert store.get_active(old.agms)["event_id"] == replacement["event_id"]
            print(f"EXIT_{booth}_REJECTED_OLD_HANDOFF_NO_REPEAT: PASS")

    # Uncertain central state: never invent END if the old exact session is
    # still actually active centrally. A rejected local END cannot be retried.
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        store = MOD.SharedEventStore(base / "shared")
        journal = MOD.OfflineJournal(base / "local")
        p = officer(99010)
        MOD.socket.gethostname = lambda: "EXIT-10"
        os.environ["USERNAME"] = "OLD"
        start = journal.enqueue("START", p, "10", "ΕΞΟΔΟΣ", "FIRST")
        journal.sync(store, MOD.PersonnelRecord)
        os.environ["USERNAME"] = "NEW"
        ids = journal.auto_close_previous_windows_users("EXIT-10", "NEW")
        assert len(ids) == 1
        journal._mark(ids[0], "CONFLICT", "manual review")
        journal.resolve_conflict(ids[0], "OFFICER_AXYP", "Verify central before real END")
        for username in ("THIRD", "FOURTH", "FIFTH"):
            assert journal.auto_close_previous_windows_users("EXIT-10", username) == []
        journal.sync(store, MOD.PersonnelRecord)
        assert journal.local_active(p.agms)["event_id"] == start["operation_id"]
        assert store.get_active(p.agms)["event_id"] == start["operation_id"]
        assert not list(store.audit.glob("offline_handoff_reconciliations/*rejected_cache.json"))
        print("UNCERTAIN_OLD_START_NOT_FALSIFIED: PASS")
finally:
    MOD.socket.gethostname = hostname
    if old_username is None:
        os.environ.pop("USERNAME", None)
    else:
        os.environ["USERNAME"] = old_username

print("REPEATED_WINDOWS_LOGIN_STALE_HANDOFF_REGRESSION: PASS")

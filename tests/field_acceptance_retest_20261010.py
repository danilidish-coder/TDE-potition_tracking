"""Field acceptance regressions from 2026-10-10 incidents.

Two EXIT PCs, old Windows-user handoff, officer moving elsewhere,
WinError 1326, forced program termination and outbox persistence.
These are simulated SMB conditions, not an on-site network certificate.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def officer(i):
    return MOD.PersonnelRecord(str(i), "ΑΣΤ", f"SURNAME{i}", "TEST")


def assert_newer_active(store, person, event):
    active = store.get_active(person.agms)
    assert active and active["event_id"] == event["event_id"], (person.agms, active, event)


if len(sys.argv) > 1 and sys.argv[1] == "--child-kill":
    root = Path(sys.argv[2])
    journal = MOD.OfflineJournal(root)
    event = journal.enqueue("START", officer(84001), "8", "ΕΞΟΔΟΣ", "CRASH_RECOVERY_TEST")
    print(json.dumps(event, ensure_ascii=True), flush=True)
    time.sleep(20)
    raise SystemExit(0)

# A: two different exit booths; operator A moves elsewhere before the local
# old-Windows-user END reaches the central AXYP; B must still claim the booth.
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    store = MOD.SharedEventStore(root / "AXYP" / "TDE_DATA")
    base_hostname = MOD.socket.gethostname
    original_user = os.environ.get("USERNAME")
    try:
        old_journals = []
        moved_officers = []
        new_officers = []
        for i, booth in enumerate((8, 9)):
            machine = f"EXIT-{booth:02d}"
            old = officer(81000 + i)
            new = officer(82000 + i)
            journal = MOD.OfflineJournal(root / f"EXIT_{booth}" / "machine_queue")
            MOD.socket.gethostname = lambda machine=machine: machine
            os.environ["USERNAME"] = f"OLD_{booth}"
            prior = journal.enqueue("START", old, str(booth), "ΕΞΟΔΟΣ", f"C_OLD_{booth}")
            report = journal.sync(store, MOD.PersonnelRecord)
            assert report["pending"] == 0 and not report["conflicts"], report
            assert store.get_active(old.agms)["event_id"] == prior["operation_id"]
            old_journals.append((machine, journal, old, new, booth, prior))

        # The old officers legitimately move to distinct new booths.
        for machine, journal, old, new, booth, prior in old_journals:
            store.end(old)
            replacement = store.start(
                old, str(booth + 4), "ΕΞΟΔΟΣ",
                origin_computer=f"EXIT-{booth+4:02d}", origin_user=f"OLD_{booth}",
            )
            moved_officers.append((old, replacement))

        # New user logs onto each of the original two machines; they do NOT
        # know how to end the old worker's session manually.
        for machine, journal, old, new, booth, prior in old_journals:
            MOD.socket.gethostname = lambda machine=machine: machine
            os.environ["USERNAME"] = f"NEW_{booth}"
            handoffs = journal.auto_close_previous_windows_users(machine, f"NEW_{booth}")
            assert len(handoffs) == 1, (booth, handoffs)
            new_start = journal.enqueue("START", new, str(booth), "ΕΞΟΔΟΣ", f"C_NEW_{booth}")
            new_officers.append((journal, new, new_start, handoffs[0], prior, old, booth))

        # Simulate an already-stored v1.2.5 conflict on one booth.
        old_conflict = old_journals[0][1]._rows(("PENDING",))[0]
        old_journals[0][1]._mark(old_conflict["id"], "CONFLICT", "Legacy old user handoff")

        for journal, new, new_start, handoff, prior, old, booth in new_officers:
            report = journal.sync(store, MOD.PersonnelRecord)
            assert report["pending"] == 0 and not report["conflicts"], (booth, report)
            assert store.get_active(new.agms)["event_id"] == new_start["operation_id"]
            assert journal.sync(store, MOD.PersonnelRecord)["applied"] == []
        for old, replacement in moved_officers:
            assert_newer_active(store, old, replacement)
        assert sorted(x["position"] for x in store.active_all()) == ["12", "13", "8", "9"]
        print("TWO_EXIT_BOOTH_HANDOFF: PASS (old worker moving, new logon, legacy conflict)")
    finally:
        MOD.socket.gethostname = base_hostname
        if original_user is None:
            os.environ.pop("USERNAME", None)
        else:
            os.environ["USERNAME"] = original_user


# B: both EXIT PCs fail with Windows login/SMB error 1326, all entries remain
# locally durable; after restarting a Python process and central recovery,
# every record must be applied once and visible in the officer's live view.
with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    store = MOD.SharedEventStore(root / "central" / "TDE_DATA")
    from types import SimpleNamespace
    failing = SimpleNamespace(
        get_active=store.get_active,
        _atomic_json=store._atomic_json,
        audit=store.audit,
        start=lambda *a, **k: (_ for _ in ()).throw(PermissionError("[WinError 1326] Wrong password")),
    )
    for i, booth in enumerate((8, 9)):
        person = officer(83000 + i)
        journal_root = root / f"EXIT_{booth}" / "machine_queue"
        journal = MOD.OfflineJournal(journal_root)
        op = journal.enqueue("START", person, str(booth), "ΕΞΟΔΟΣ", f"CLIENT_{booth}")
        response = journal.sync(failing, MOD.PersonnelRecord)
        assert "1326" in response["network_error"], response
        assert response["pending"] == 1 and not response["applied"], response
        assert store.get_active(person.agms) is None
        del journal  # simulates next process opening the same machine state
        reopened = MOD.OfflineJournal(journal_root)
        applied = reopened.sync(store, MOD.PersonnelRecord)
        assert applied["pending"] == 0 and not applied["conflicts"], applied
        assert store.get_active(person.agms)["event_id"] == op["operation_id"]
        assert reopened.sync(store, MOD.PersonnelRecord)["applied"] == []
    assert len(store.active_all()) == 2
    print("TWO_EXIT_AUTH_FAILURE_AND_RECOVERY: PASS (1326, local persistence, exactly-once)")


# C: emulate the operator forcibly terminating the process after enqueue()
# committed to disk, then reopening on the same machine without any manual fix.
# It cannot prove the Qt window watchdog, but tests persistence across a kill.
with tempfile.TemporaryDirectory() as d:
    journal_root = Path(d) / "local"
    central = MOD.SharedEventStore(Path(d) / "central" / "TDE_DATA")
    process = subprocess.Popen(
        [sys.executable, "-u", str(Path(__file__).resolve()), "--child-kill", str(journal_root)],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    try:
        receipt_line = process.stdout.readline().strip()
        assert receipt_line.startswith("{"), receipt_line
        operation = json.loads(receipt_line)
        process.kill()
        process.wait(timeout=12)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=12)
    reopened = MOD.OfflineJournal(journal_root)
    assert reopened.pending_count() == 1
    recovered = reopened.sync(central, MOD.PersonnelRecord)
    assert recovered["pending"] == 0 and not recovered["conflicts"], recovered
    assert central.get_active("84001")["event_id"] == operation["operation_id"]
    assert reopened.sync(central, MOD.PersonnelRecord)["applied"] == []
    print("FORCED_PROCESS_TERMINATION_RECOVERY: PASS (journal restart, exact IDs)")

print("FIELD_ACCEPTANCE_RETEST_COMPLETE: PASS")

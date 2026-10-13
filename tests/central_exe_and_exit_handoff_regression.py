"""Protect the central-SCAN deployment and the real EXIT handoff scenario.

All workstations launch the one central EXE; no local auto-cache or shortcut
overwrite. A superseded auto-END conflict on officer A must not block officer
B's START at the freed EXIT booth.
"""
from __future__ import annotations
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"src"/"position_tracking.py").read_text(encoding="utf-8")
assert 'APP_VERSION = "1.2.10"' in source
assert "cache_windows_client(" not in source, "Application is still copying shared EXE to the terminal"
assert "from position_tracking_bootstrap import" not in source, "Bootstrap can still redirect Desktop shortcut"
assert "from position_tracking_offline import OfflineJournal" in source
assert "self.offline.auto_close_previous_windows_users(" in source
print("CENTRAL_EXE_NO_LOCAL_AUTO_SHORTCUT: PASS")

SPEC=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
MOD=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=MOD
SPEC.loader.exec_module(MOD)

def person(n):
    return MOD.PersonnelRecord(str(n),"AST",f"FAMILY{n}","NAME")

previous_hostname=MOD.socket.gethostname
previous_user=os.environ.get("USERNAME")
try:
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        store=MOD.SharedEventStore(root/"shared"/"TDE_DATA")
        journal=MOD.OfflineJournal(root/"public"/"machine_queue")
        old,new=person(99301),person(99302)
        MOD.socket.gethostname=lambda:"EXIT-09"
        os.environ["USERNAME"]="PREVIOUS_WINDOWS_USER"
        recorded=journal.enqueue("START",old,"9","ΕΞΟΔΟΣ","CLIENT_OLD")
        assert journal.sync(store,MOD.PersonnelRecord)["pending"]==0
        assert store.get_active(old.agms)["event_id"]==recorded["operation_id"]

        # Officer A exits EXIT-09 and now works elsewhere.
        store.end(old)
        new_old_session=store.start(old,"13","ΕΞΟΔΟΣ",
            origin_computer="EXIT-13",origin_user="PREVIOUS_WINDOWS_USER")
        os.environ["USERNAME"]="CURRENT_WINDOWS_USER"
        ended=journal.auto_close_previous_windows_users("EXIT-09","CURRENT_WINDOWS_USER")
        assert len(ended)==1
        journal._mark(ended[0],"CONFLICT","Old offline END rejected")
        assert len(journal.conflicts())==1

        # A different officer's START was never supposed to be blocked by
        # the prior officer's END conflict. This guards that behavior.
        started=journal.enqueue("START",new,"9","ΕΞΟΔΟΣ","CLIENT_NEW")
        report=journal.sync(store,MOD.PersonnelRecord)
        assert report["pending"]==0,report
        assert report["conflicts"]==[],report
        assert store.get_active(new.agms)["event_id"]==started["operation_id"]
        assert store.get_active(old.agms)["event_id"]==new_old_session["event_id"]
        assert journal.local_active(old.agms)["event_id"]==new_old_session["event_id"]

        # Consecutive new Windows logins must not re-create an END for the
        # former officer; the *current* holder may be closed normally.
        os.environ["USERNAME"]="NEXT_WINDOWS_USER"
        journal.auto_close_previous_windows_users("EXIT-09","NEXT_WINDOWS_USER")
        previous_ends=[r for r in journal._rows(("PENDING","APPLIED","CONFLICT","RECONCILED","REJECTED"))
                       if r["agms"]==old.agms and r["kind"]=="END"]
        assert len(previous_ends)==1,previous_ends
        assert store.get_active(old.agms)["event_id"]==new_old_session["event_id"]
        print("EXIT_OLD_END_CONFLICT_NEW_OFFICER_NOT_BLOCKED: PASS")
finally:
    MOD.socket.gethostname=previous_hostname
    if previous_user is None:os.environ.pop("USERNAME",None)
    else:os.environ["USERNAME"]=previous_user

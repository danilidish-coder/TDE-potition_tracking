"""Audit: central committed START, workstation lost acknowledgement,
old officer moved, supervisor rejected late END. No unsent work may be stuck.
"""
import importlib.util
import os
from datetime import datetime
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

def person(i):return mod.PersonnelRecord(str(i),"AST","SURNAME"+str(i),"TEST")
with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    store=mod.SharedEventStore(root/"central")
    journal=mod.OfflineJournal(root/"local")
    old,new=person(99670),person(99671)
    os.environ["USERNAME"]="OLD_ACCOUNT"
    original_host=mod.socket.gethostname
    try:
        mod.socket.gethostname=lambda:"EXIT-08"
        old_local=journal.enqueue("START",old,"8","ΕΞΟΔΟΣ","OLD")
        # Host committed this exact START but the ACK did not reach local journal.
        central_old=store.start(old,"8","ΕΞΟΔΟΣ",
            when=datetime.fromisoformat(old_local["timestamp"]),
            event_id=old_local["operation_id"],
            origin_computer="EXIT-08",origin_user="OLD_ACCOUNT")
        assert journal._rows(("PENDING",))[0]["kind"]=="START"
        # Old officer legitimately moved to EXIT-12 in meantime.
        store.end(old)
        replacement=store.start(old,"12","ΕΞΟΔΟΣ",
           origin_computer="EXIT-12",origin_user="OLD_ACCOUNT")
        os.environ["USERNAME"]="NEW_ACCOUNT"
        auto=journal.auto_close_previous_windows_users("EXIT-08","NEW_ACCOUNT")
        assert len(auto)==1,auto
        journal._mark(auto[0],"CONFLICT","Old handoff superseded")
        journal.resolve_conflict(auto[0],"AXYP_ID","Confirmed old officer works elsewhere")
        new_local=journal.enqueue("START",new,"8","ΕΞΟΔΟΣ","NEW")
        report=journal.sync(store,mod.PersonnelRecord)
        print("LOST_ACK_REJECTED_END_REPORT:",report,flush=True)
        assert report["network_error"]=="", "A permanently stale prior START must not halt the entire outbox"
        assert report["pending"]==0, "Old or new local operations remained unsent"
        assert not report["conflicts"], "Expected safe automatic reconciliation"
        assert store.get_active(old.agms)["event_id"]==replacement["event_id"]
        assert store.get_active(new.agms)["event_id"]==new_local["operation_id"]
        print("LOST_ACK_REJECTED_END_NEW_USER_SYNC: PASS")
    finally:
        mod.socket.gethostname=original_host

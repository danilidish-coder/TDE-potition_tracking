"""Release-blocker regression for the KNOWN v1.2.5 stale observed AGMS.

Expected to FAIL on uncorrected v1.2.5; only temporary test data used.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
pt=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=pt
spec.loader.exec_module(pt)
previous_host=pt.socket.gethostname
previous_user=os.environ.get("USERNAME")
try:
    with tempfile.TemporaryDirectory(prefix="kp-stale-regression-") as folder:
        base=Path(folder)
        host="EXIT-08"
        pt.socket.gethostname=lambda:host
        os.environ["USERNAME"]="USER_A"
        store=pt.SharedEventStore(base/"central"/"TDE_DATA")
        machine=base/"local"/"machine_journal"
        journal=pt.OfflineJournal(machine)
        person=pt.PersonnelRecord("9101","ΑΣΤ","TEST","OFFICER")
        old=journal.enqueue("START",person,"8","ΕΞΟΔΟΣ","CLIENT_A")
        outcome=journal.sync(store,pt.PersonnelRecord)
        assert outcome["pending"]==0 and not outcome["conflicts"],outcome
        old_id=old["operation_id"]
        assert journal.local_active(person.agms)["event_id"]==old_id

        # Central truth changes while local SQLite still reflects old position.
        store.end(person)
        newer=store.start(person,"13","ΕΞΟΔΟΣ",origin_computer="EXIT-13",origin_user="USER_A")
        assert newer["event_id"]!=old_id
        os.environ["USERNAME"]="USER_B"
        ids=journal.auto_close_previous_windows_users(host,"USER_B")
        assert len(ids)==1
        outcome=journal.sync(store,pt.PersonnelRecord)
        assert len(outcome["conflicts"])==1
        journal.resolve_conflict(ids[0],"AXYP_01","Confirmed stale prior event on other booth")
        assert not journal.conflicts()

        # Simulated Windows session restart with SAME durable local DB.
        journal=pt.OfflineJournal(machine)
        local=journal.local_active(person.agms)
        assert not local or local.get("event_id")!=old_id, (
            "RELEASE BLOCKED: stale rejected AGMS remains cached in SQLite")
        assert journal.auto_close_previous_windows_users(host,"USER_C")==[], (
            "RELEASE BLOCKED: same obsolete handoff re-created")
        print("STALE_AGMS_AFTER_REJECTION: PASS")
finally:
    pt.socket.gethostname=previous_host
    if previous_user is None:os.environ.pop("USERNAME",None)
    else:os.environ["USERNAME"]=previous_user

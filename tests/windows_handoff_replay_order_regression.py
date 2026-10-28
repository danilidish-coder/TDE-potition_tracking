"""Stage 3b: Central handoff MUST complete before offline START replay.

Regression scenarios reflect reported EXIT booth failures: two Windows logins on
one terminal, cached legacy central active, pending original END, offline
previous-user START/END, lost SMB host, 14 simultaneously occupied booths,
unrelated computer, and missing identity.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
SPEC=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
MOD=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name]=MOD
SPEC.loader.exec_module(MOD)
from position_tracking_handoff import HandoffBlocked, reconcile_handoff_before_replay

def person(n):
    return MOD.PersonnelRecord(str(n),"ΑΣΤ",f"PERSON{n}","TEST")

def identity(machine,user):
    return patch.dict(os.environ,{"USERNAME":user,"USER":user})

def replay(store,journal,machine,user):
    return reconcile_handoff_before_replay(store,journal,MOD.PersonnelRecord,machine,user)

def all_ends(store,agms):
    return [x for x in store.iter_all_events() if x.get("kind")=="END" and x.get("agms")==agms]

# This backend stage intentionally runs with stdlib only. Inspect the actual
# linked controller methods without importing Qt presentation dependencies.
import ast
main_source=ROOT/"src"/"position_tracking_ui_main.py"
if not main_source.exists():main_source=ROOT/"src"/"position_tracking.py"
main_tree=ast.parse(main_source.read_text(encoding="utf-8"))
window=next(n for n in ast.walk(main_tree) if isinstance(n,ast.ClassDef) and n.name=="MainWindow")

def controller_method(module, owner, name):
    assert any(isinstance(b,ast.Name) and b.id==owner for b in window.bases), "Controller must be linked to actual MainWindow"
    source=(ROOT/"src"/(module+".py")).read_text(encoding="utf-8")
    cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name==owner)
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
    return ast.get_source_segment(source,method)

communication=controller_method("position_tracking_ui_communication","CommunicationMixin","_communication_io")
worker=controller_method("position_tracking_ui_positions","PositionActionsMixin","_offline_tick")
assert "close_previous_windows_user_positions(" not in communication, "Independent heartbeat must never overtake original offline END"
assert "reconcile_handoff_before_replay(" in worker, "Worker must resolve central handoff BEFORE replaying offline"
assert "report = self.offline.sync(store" not in worker, "Old sync-before-handoff regression"

# 1. Original bug: central old START on EXIT booth, then new account pending START.
with tempfile.TemporaryDirectory() as tmp:
    store=MOD.SharedEventStore(Path(tmp)/"shared")
    journal=MOD.OfflineJournal(Path(tmp)/"machine")
    old,new,other=person(72001),person(72002),person(72003)
    prior=store.start(old,"8","ΕΞΟΔΟΣ",origin_computer="BOOTH-08",origin_user="ACCOUNT_A")
    keep=store.start(other,"9","ΕΞΟΔΟΣ",origin_computer="BOOTH-09",origin_user="ACCOUNT_A")
    with identity("BOOTH-08","ACCOUNT_B"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        op=journal.enqueue("START",new,"8","ΕΞΟΔΟΣ","B_CLIENT")
        before=json.loads(json.dumps(journal._rows(("PENDING",))[0]))
        result=replay(store,journal,"BOOTH-08","ACCOUNT_B")
        # D1: a different Windows user cannot implicitly release the booth.
        # Preserve the queued conflicting command, its ID/time and both STARTs.
        assert result["conflicts"] and result["applied"] == [], result
        assert store.get_active(old.agms)["event_id"] == prior["event_id"]
        assert store.get_active(new.agms) is None
        assert store.get_active(other.agms)["event_id"] == keep["event_id"]
        assert all_ends(store, old.agms) == []
        retained = journal._rows(("CONFLICT",))
        assert len(retained) == 1
        assert retained[0]["id"] == before["id"]
        assert retained[0]["created_at"] == before["created_at"]
        assert replay(store,journal,"BOOTH-08","ACCOUNT_B")["applied"] == []

# 2. Durable old-user END has priority: preserve its original ID/timestamp.
with tempfile.TemporaryDirectory() as tmp:
    store=MOD.SharedEventStore(Path(tmp)/"shared")
    journal=MOD.OfflineJournal(Path(tmp)/"machine")
    old=person(72101)
    start=store.start(old,"8","ΕΞΟΔΟΣ",origin_computer="BOOTH-08",origin_user="ACCOUNT_A")
    journal.remember(old.agms,start)
    with identity("BOOTH-08","ACCOUNT_A"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        end=journal.enqueue("END",old,client_id="ORIGINAL_CLIENT",reason="ORIGINAL_EXPLICIT_END")
    pending=journal._rows(("PENDING",))[0]
    assert pending["start_id"]==start["event_id"]
    with identity("BOOTH-08","ACCOUNT_B"):
        result=replay(store,journal,"BOOTH-08","ACCOUNT_B")
    assert not result["conflicts"] and result["pending"]==0,result
    ends=all_ends(store,old.agms)
    assert len(ends)==1 and ends[0]["event_id"]==end["operation_id"],ends
    assert ends[0]["timestamp"]==pending["created_at"]
    assert ends[0]["start_event_id"]==start["event_id"]
    assert ends[0].get("end_reason")=="ORIGINAL_EXPLICIT_END"
    assert store.get_active(old.agms) is None

# 3. Old user START never reached server. Local recovery queues END before
#    next Windows user START, and server replays original three operations.
with tempfile.TemporaryDirectory() as tmp:
    store=MOD.SharedEventStore(Path(tmp)/"shared")
    journal=MOD.OfflineJournal(Path(tmp)/"machine")
    old,new=person(72201),person(72202)
    with identity("BOOTH-08","ACCOUNT_A"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        old_start=journal.enqueue("START",old,"8","ΕΞΟΔΟΣ","OLD")
    with identity("BOOTH-08","ACCOUNT_B"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        closed=journal.auto_close_previous_windows_users("BOOTH-08","ACCOUNT_B")
        assert len(closed)==1
        new_start=journal.enqueue("START",new,"8","ΕΞΟΔΟΣ","NEW")
        result=replay(store,journal,"BOOTH-08","ACCOUNT_B")
    assert result["pending"]==0 and len(result["applied"])==3,result
    assert store.get_active(old.agms) is None
    assert store.get_active(new.agms)["event_id"]==new_start["operation_id"]
    ends=all_ends(store,old.agms)
    assert len(ends)==1 and ends[0]["start_event_id"]==old_start["operation_id"]
    assert ends[0].get("end_reason")=="WINDOWS_USER_HANDOFF_OFFLINE"
    assert result["applied"]==[old_start["operation_id"],closed[0],new_start["operation_id"]]
    assert journal.sync(store,MOD.PersonnelRecord)["applied"]==[]

# 4. A genuinely unavailable SMB server must NOT consume or mark pending START.
with tempfile.TemporaryDirectory() as tmp:
    journal=MOD.OfflineJournal(Path(tmp)/"machine")
    new=person(72301)
    with identity("BOOTH-08","ACCOUNT_B"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        op=journal.enqueue("START",new,"8","ΕΞΟΔΟΣ","NEW")
    class Unavailable:
        def close_previous_windows_user_positions(self,*args,**kwargs):
            raise OSError("SIMULATED_SMB_UNAVAILABLE")
    try:
        replay(Unavailable(),journal,"BOOTH-08","ACCOUNT_B")
    except OSError as exc:
        assert "SIMULATED_SMB_UNAVAILABLE" in str(exc)
    else:
        raise AssertionError("SMB failure ignored and START potentially consumed")
    assert journal._rows(("PENDING",))[0]["id"]==op["operation_id"]
    assert journal.pending_count()==1

# 5. Missing Windows identity or preexisting conflict must not falsely close.
with tempfile.TemporaryDirectory() as tmp:
    store=MOD.SharedEventStore(Path(tmp)/"shared")
    journal=MOD.OfflineJournal(Path(tmp)/"machine")
    old,new=person(72401),person(72402)
    store.start(old,"8","ΕΞΟΔΟΣ",origin_computer="BOOTH-08",origin_user="ACCOUNT_A")
    with identity("BOOTH-08","ACCOUNT_B"),patch.object(socket,"gethostname",return_value="BOOTH-08"):
        op=journal.enqueue("START",new,"8","ΕΞΟΔΟΣ","B")
    for computer,user in (("", "ACCOUNT_B"),("BOOTH-08","")):
        try:replay(store,journal,computer,user)
        except HandoffBlocked:pass
        else:raise AssertionError("Unknown identity allowed unsafe close")
    assert store.get_active(old.agms) is not None
    assert journal.pending_count()==1
    journal._mark(op["operation_id"],"CONFLICT","TEST_EXISTING_CONFLICT")
    result=replay(store,journal,"BOOTH-08","ACCOUNT_B")
    assert result["conflicts"] and result["applied"]==[]
    assert store.get_active(old.agms) is not None

# 6. Multiple real stations: 14 occupied positions (7 EXIT); every booth
#    handoff should be isolated and all original start IDs preserved.
with tempfile.TemporaryDirectory() as tmp:
    store=MOD.SharedEventStore(Path(tmp)/"shared")
    sessions=[]
    for i in range(1,15):
        machine=f"BOOTH-{i:02}"
        old=person(74000+i)
        new=person(75000+i)
        direction="ΕΞΟΔΟΣ" if i>=8 else "ΕΙΣΟΔΟΣ"
        prior=store.start(old,str(i),direction,origin_computer=machine,origin_user="ACCOUNT_A")
        journal=MOD.OfflineJournal(Path(tmp)/f"machine_{i:02}")
        with identity(machine,"ACCOUNT_B"),patch.object(socket,"gethostname",return_value=machine):
            nxt=journal.enqueue("START",new,str(i),direction,f"CLIENT_{i:02}")
        sessions.append((machine,old,new,prior,nxt,journal))
    for machine,old,new,prior,nxt,journal in reversed(sessions):
        result=replay(store,journal,machine,"ACCOUNT_B")
        assert result["conflicts"] and result["applied"] == [], (machine,result)
        assert store.get_active(old.agms)["event_id"] == prior["event_id"]
        assert store.get_active(new.agms) is None
        assert all_ends(store,old.agms) == []
        assert journal._rows(("CONFLICT",))[0]["id"] == nxt["operation_id"]
    assert len(store.active_all())==14
    assert sum(1 for x in store.active_all() if x["direction"]=="ΕΞΟΔΟΣ")==7

print("WINDOWS_HANDOFF_REPLAY_ORDER: PASS (EXIT, old END identity/time, 14 booths, network outage, conflicts)")

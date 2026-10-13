"""Offline durable outbox, delayed ACK idempotence, race/conflict and replay."""
import importlib.util
import json
import os
import tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('position_tracking', ROOT/'src'/'position_tracking.py')
MOD=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)


def person(n):return MOD.PersonnelRecord(str(n),'ΑΣΤ',f'SURNAME{n}','NAME')

with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    central=MOD.SharedEventStore(root/'host'/'TDE_DATA')
    client1=MOD.OfflineJournal(root/'clients'/'booth1')
    client2=MOD.OfflineJournal(root/'clients'/'booth2')
    a,b,c=person(800001),person(800002),person(800003)
    # Outage: two stations independently think booth 3 is available.
    qa=client1.enqueue('START',a,'3','ΕΙΣΟΔΟΣ','CLIENT1')
    qb=client2.enqueue('START',b,'3','ΕΙΣΟΔΟΣ','CLIENT2')
    assert client1.pending_count()==1 and client2.pending_count()==1
    assert client1.local_active(a.agms)['offline_status']=='PENDING'
    assert central.active_all()==[]
    # restart local app, queue remains durable and can end own queued start
    client1=MOD.OfflineJournal(root/'clients'/'booth1')
    x=client1.enqueue('END',a,client_id='CLIENT1')
    assert client1.pending_count()==2 and client1.local_active(a.agms) is None
    # Simulate central returning: replay original times/IDs and release booth.
    r=client1.sync(central,MOD.PersonnelRecord)
    assert r['pending']==0 and len(r['applied'])==2
    assert central.get_active(a.agms) is None
    ended=[v for v in central.iter_all_events() if v.get('kind')=='END' and v.get('agms')==a.agms]
    assert len(ended)==1 and ended[0]['start_event_id']==qa['operation_id']
    assert ended[0]['event_id']==x['operation_id']
    assert client1.sync(central,MOD.PersonnelRecord)['applied']==[]
    assert client2.sync(central,MOD.PersonnelRecord)['pending']==0
    assert central.get_active(b.agms)['event_id']==qb['operation_id']
    # Network response disappears after central ACK, resubmitting same ID safe.
    assert central.start(b,'3','ΕΙΣΟΔΟΣ',event_id=qb['operation_id'])['event_id']==qb['operation_id']
    assert len([v for v in central.iter_all_events() if v.get('kind')=='START' and v.get('agms')==b.agms])==1
    # Someone else occupies booth 3 offline; conflict is preserved, not overwritten.
    client3=MOD.OfflineJournal(root/'clients'/'booth3')
    qc=client3.enqueue('START',c,'3','ΕΙΣΟΔΟΣ','CLIENT3')
    res=client3.sync(central,MOD.PersonnelRecord)
    assert len(res['conflicts'])==1 and client3.pending_count()==1
    assert central.get_active(b.agms)['event_id']==qb['operation_id']
    assert central.get_active(c.agms) is None
    try:
        client3.enqueue('END',c,client_id='CLIENT3')
        raise AssertionError('unresolved conflict wrongly allowed more operations')
    except MOD.OfflineConflict:
        pass
    # Offline END of previously confirmed central START; do not lose END.
    client4=MOD.OfflineJournal(root/'clients'/'booth4')
    client4.remember(b.agms,central.get_active(b.agms))
    client4.enqueue('END',b,client_id='CLIENT2')
    assert client4.local_active(b.agms) is None
    assert client4.sync(central,MOD.PersonnelRecord)['pending']==0
    assert central.get_active(b.agms) is None

print('OFFLINE_RECOVERY_INTEGRATION: PASS')

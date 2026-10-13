"""Two different Windows users on ONE terminal and a vanished central host."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('position_tracking',ROOT/'src'/'position_tracking.py')
MOD=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

def person(i): return MOD.PersonnelRecord(str(i),'ΑΣΤ',f'SURNAME{i}', 'NAME')
with tempfile.TemporaryDirectory() as d:
    home=Path(d)
    store=MOD.SharedEventStore(home/'share'/'TDE_DATA')
    journal=MOD.OfflineJournal(home/'public'/'machine_queue')
    a,b=person(118001),person(118002)
    original=MOD.socket.gethostname
    MOD.socket.gethostname=lambda:'BOOTH-07'
    os.environ['USERNAME']='ACCOUNT_A'
    first=journal.enqueue('START',a,'7','ΕΙΣΟΔΟΣ','APP_A')
    assert journal.local_active(a.agms)['event_id']==first['operation_id']
    # User A signs out while the central share is unavailable.
    os.environ['USERNAME']='ACCOUNT_B'
    journal=MOD.OfflineJournal(home/'public'/'machine_queue')
    completed=journal.auto_close_previous_windows_users('BOOTH-07', 'ACCOUNT_B')
    assert len(completed)==1
    assert journal.local_active(a.agms) is None
    assert journal.auto_close_previous_windows_users('BOOTH-07','ACCOUNT_B')==[]
    second=journal.enqueue('START',b,'7','ΕΙΣΟΔΟΣ','APP_B')
    assert journal.local_active(b.agms)['event_id']==second['operation_id']
    assert len(store.active_all())==0
    result=journal.sync(store,MOD.PersonnelRecord)
    assert result['pending']==0 and len(result['applied'])==3
    assert store.get_active(a.agms) is None
    assert store.get_active(b.agms)['event_id']==second['operation_id']
    entries=store.iter_all_events()
    ends=[x for x in entries if x.get('kind')=='END']
    assert len(ends)==1
    assert ends[0]['end_reason']=='WINDOWS_USER_HANDOFF_OFFLINE'
    assert ends[0]['user']=='ACCOUNT_B'
    assert journal.sync(store, MOD.PersonnelRecord)['applied']==[]
    MOD.socket.gethostname=original
print('OFFLINE_USER_LOGOFF_MACHINE_QUEUE: PASS')

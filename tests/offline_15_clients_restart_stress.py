"""Offline 15 separate simulated booth processes and queued power-loss replay."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
THIS = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location('position_tracking',ROOT/'src'/'position_tracking.py')
MOD = importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

def person(i):return MOD.PersonnelRecord(str(i),'ΑΣΤ',f'PERSON{i}','OFFLINE')

def one(home, idx, position):
    env={**os.environ,'USERNAME':f'USER{idx:02d}','TDE_POSITION_MACHINE_ROOT':str(home/'public'/str(idx))}
    r=subprocess.run([sys.executable,str(THIS),'--client',str(home),str(idx),str(position)],
                     cwd=ROOT,capture_output=True,text=True,env=env,timeout=25)
    if r.returncode: raise AssertionError(f'client {idx} failed: {r.stdout} {r.stderr}')
    return json.loads(r.stdout.strip().splitlines()[-1])

if len(sys.argv)>1 and sys.argv[1]=='--client':
    home=Path(sys.argv[2]); idx=int(sys.argv[3]); pos=sys.argv[4]
    person_i=person(9000+idx)
    journal=MOD.OfflineJournal(home/'public'/str(idx))
    receipt=journal.enqueue('START',person_i,pos,'ΕΙΣΟΔΟΣ',client_id=f'C{idx}')
    print(json.dumps(receipt));raise SystemExit(0)

with tempfile.TemporaryDirectory() as d:
    home=Path(d); share=home/'AXYP_SHARED'/'TDE_DATA'
    store=MOD.SharedEventStore(share)
    # Simulated AXYP computer offline: central data moved out of reach.
    parent=share.parent; hidden=home/'AXYP_POWERED_OFF'
    parent.rename(hidden)
    with ThreadPoolExecutor(max_workers=15) as pool:
        replies=list(pool.map(lambda i:one(home,i,str(i if i<=14 else 1)),range(1,16)))
    assert len(replies)==15 and all(x['pending_sync'] for x in replies)
    assert not share.exists()
    hidden.rename(parent)
    # 14 distinct booths, one duplicate. All offline requests must survive
    # independent process exits (Windows user logout/power down).
    journal_list=[MOD.OfflineJournal(home/'public'/str(i)) for i in range(1,16)]
    assert sum(j.pending_count() for j in journal_list)==15
    applied=0; conflict=0
    for j in journal_list:
        r=j.sync(store,MOD.PersonnelRecord)
        applied+=len(r['applied']); conflict+=len(r['conflicts'])
    assert applied==14 and conflict==1,(applied,conflict)
    assert len(store.active_all())==14
    assert len({x['position'] for x in store.active_all()})==14
    assert sum(j.pending_count() for j in journal_list)==1
    assert sum(len(j.sync(store,MOD.PersonnelRecord)['applied']) for j in journal_list)==0
    wrong=next(j for j in journal_list if j.conflicts())
    cid=wrong.conflicts()[0]['id']
    assert wrong.resolve_conflict(cid,'999999','Επιβεβαιωμένα διαφορετική θέση')
    assert wrong.pending_count()==0
    assert len(store.active_all())==14
print('OFFLINE_15_CLIENTS_RESTART_STRESS: PASS')

"""Windows SMB-style lock contention: no write BEFORE acquiring the lock."""
from __future__ import annotations
import importlib.util
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('position_tracking',ROOT/'src'/'position_tracking.py')
MOD=importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name]=MOD
SPEC.loader.exec_module(MOD)

def person(i):
    return MOD.PersonnelRecord(str(i),'ΑΣΤ',f'RACE{i}','BOOTH')

with tempfile.TemporaryDirectory(prefix='TDE-lock-parallel-') as folder:
    for cycle in range(6):
        store=MOD.SharedEventStore(Path(folder)/str(cycle))
        def start(i):
            try:
                return store.start_officer_shift(person(10000+cycle*50+i))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            result=list(pool.map(start,range(12)))
        ok=[x for x in result if x]
        assert len(ok)==1,(cycle,result)
        assert store.current_shift()['shift_id']==ok[0]['shift_id']
        assert store._lock_path('__SHIFT_CONTROL__').exists()
        with store.officer_lock('__SHIFT_CONTROL__',timeout=4):
            pass
print('SHARED_FILE_LOCK_CONCURRENCY: PASS (72 attempts, 6 fresh lock files)')

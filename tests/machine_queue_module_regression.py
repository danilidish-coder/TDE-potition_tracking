"""Machine-wide offline queue security contracts, without GUI or admin rights."""
from __future__ import annotations
import ast
import importlib.util
import os
from pathlib import Path
from unittest.mock import patch
import tempfile
import sqlite3
from contextlib import closing

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('position_tracking_machine_queue',ROOT/'src'/'position_tracking_machine_queue.py')
assert SPEC and SPEC.loader
mq=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mq)
tree=ast.parse((ROOT/'src'/'position_tracking.py').read_text(encoding='utf-8'))
assert not any(isinstance(x,ast.FunctionDef) and x.name in ('_local_root','_machine_queue_root') for x in tree.body)
assert any(isinstance(x,ast.ImportFrom) and x.module=='position_tracking_machine_queue'
               and {'_local_root','_machine_queue_root'}<={y.name for y in x.names} for x in tree.body)

with tempfile.TemporaryDirectory() as root:
    base=Path(root);public=base/'PUBLIC';a=base/'User_A';b=base/'User_B'
    def resolve(account,explicit=''):
        with patch.dict(os.environ,{'PUBLIC':str(public),'LOCALAPPDATA':str(account),
                                    'TDE_POSITION_MACHINE_ROOT':str(explicit)},clear=False):
            return mq._machine_queue_root()
    path=resolve(a)
    assert path==resolve(b)==public/'Documents'/'TDE_Krystallopigis'/'PositionTracking_Queue'
    assert not list(path.glob('.writecheck_*'))
    original_write=Path.write_bytes
    def simulate_denied(self,payload):
        if self.name.startswith('.writecheck_'):raise PermissionError('SIMULATED PUBLIC ACL DENIED')
        return original_write(self,payload)
    for user in (a,b):
        with patch.dict(os.environ,{'PUBLIC':str(public),'LOCALAPPDATA':str(user),
                                    'TDE_POSITION_MACHINE_ROOT':''},clear=False):
            with patch.object(Path,'write_bytes',simulate_denied):
                try:mq._machine_queue_root()
                except RuntimeError as exc:
                    assert 'ΚΟΙΝΗ ΟΥΡΑ' in str(exc) and 'προσωπικός' in str(exc),str(exc)
                else:raise AssertionError('Unsafe silent per-user fallback')
    legacy=a/'TDE_Krystallopigis'/'PositionTracking'/'machine_queue'/'position_outbox.sqlite3'
    legacy.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(legacy)) as db:
        db.execute('CREATE TABLE operations (id TEXT PRIMARY KEY,status TEXT)')
        db.execute("INSERT INTO operations VALUES ('original-event-id','PENDING')")
        db.commit()
    with patch.dict(os.environ,{'PUBLIC':str(public),'LOCALAPPDATA':str(a),
                                'TDE_POSITION_MACHINE_ROOT':''},clear=False):
        try:mq._machine_queue_root()
        except RuntimeError as exc:assert 'ΕΚΚΡΕΜΕΙΣ' in str(exc),str(exc)
        else:raise AssertionError('Hidden unsent original event was ignored')
    with closing(sqlite3.connect(legacy)) as db:
        assert db.execute('SELECT COUNT(*) FROM operations').fetchone()[0]==1
        db.execute("UPDATE operations SET status='APPLIED'")
        db.commit()
    assert resolve(a)==path
    assert resolve(b,base/'EXPLICIT-BOOTH-08')==base/'EXPLICIT-BOOTH-08'
    legacy.write_text('CORRUPT_SQLITE',encoding='utf-8')
    with patch.dict(os.environ,{'PUBLIC':str(public),'LOCALAPPDATA':str(a),
                                'TDE_POSITION_MACHINE_ROOT':''},clear=False):
        try:mq._machine_queue_root()
        except RuntimeError as exc:assert 'παλιά προσωπική' in str(exc)
        else:raise AssertionError('Unverified legacy queue was ignored')
if os.name=='nt':
    with patch.dict(os.environ,{'PUBLIC':'','TDE_POSITION_MACHINE_ROOT':''},clear=False):
        try:mq._machine_queue_root()
        except RuntimeError as exc:assert 'PUBLIC' in str(exc)
        else:raise AssertionError('Windows missing PUBLIC silently used a private queue')
print('MACHINE_QUEUE_MODULE: PASS (two accounts, ACL, old unsent events, corrupt queue, explicit root)')

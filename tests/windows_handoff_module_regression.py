"""Stage 3a: extracted handoff module MUST preserve all prior behavior."""
from __future__ import annotations
import ast, importlib.util, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from position_tracking_handoff import close_previous_windows_user_positions

spec=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
module=importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name]=module
spec.loader.exec_module(module)
tree=ast.parse((ROOT/"src"/"position_tracking.py").read_text(encoding="utf-8"))
assert any(isinstance(n,ast.ImportFrom) and n.module=="position_tracking_handoff" for n in tree.body)
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="SharedEventStore")
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="close_previous_windows_user_positions")
assert len(method.body)==1 and isinstance(method.body[0],ast.Return), "Handoff code must reside in its own module"

def person(n):
    return module.PersonnelRecord(str(n),"ΑΣΤ",f"SURNAME{n}","NAME")

with tempfile.TemporaryDirectory() as tmp:
    store=module.SharedEventStore(Path(tmp))
    old=person(30001)
    unrelated=person(30002)
    store.start(old,"8","ΕΞΟΔΟΣ",origin_computer="BOOTH-08",origin_user="ACCOUNT_A")
    store.start(unrelated,"9","ΕΞΟΔΟΣ",origin_computer="BOOTH-09",origin_user="ACCOUNT_A")
    first=store.get_active(old.agms)
    assert first
    assert store.close_previous_windows_user_positions("BOOTH-08","ACCOUNT_B",protected_start_ids={first["event_id"]})==[]
    assert store.get_active(old.agms)["event_id"]==first["event_id"],"Original END must win over new synthetic END"
    assert store.close_previous_windows_user_positions("BOOTH-08","ACCOUNT_A")==[], "Same Windows user must not be closed"
    assert store.close_previous_windows_user_positions("BOOTH-08","")==[], "Missing Windows identity must not end"
    closed=store.close_previous_windows_user_positions("BOOTH-08","ACCOUNT_B")
    assert len(closed)==1 and closed[0]["start_event_id"]==first["event_id"]
    assert store.get_active(old.agms) is None
    assert store.get_active(unrelated.agms) is not None
    assert store.close_previous_windows_user_positions("BOOTH-08","ACCOUNT_B")==[], "Replay must be idempotent"
    ends=[x for x in store.iter_all_events() if x.get("kind")=="END" and x.get("agms")==old.agms]
    assert len(ends)==1 and ends[0].get("end_reason")=="WINDOWS_USER_HANDOFF_RECOVERY"
print("HANDOFF_MODULE_STAGE3A: PASS (protected IDs, same PC, idempotence, unmatched PC preserved)")

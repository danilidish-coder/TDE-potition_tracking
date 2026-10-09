from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def person(i: int):
    return MOD.PersonnelRecord(str(i), "ΑΣΤ", f"USER{i}", "TEST")


def relabel(store, record, *, computer: str, user: str):
    path = store._active_path(record.agms)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["computer"] = computer
    data["user"] = user
    store._atomic_json(path, data)
    return data


with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    old = person(71001)
    other_pc = person(71002)
    same_user = person(71003)
    unknown_user = person(71004)
    for i, p in enumerate((old, other_pc, same_user, unknown_user), 1):
        store.start(p, str(i), "ΕΙΣΟΔΟΣ")
    a = relabel(store, old, computer="BOOTH-01", user="OLD_USER")
    relabel(store, other_pc, computer="BOOTH-02", user="OLD_USER")
    relabel(store, same_user, computer="BOOTH-01", user="NEW_USER")
    relabel(store, unknown_user, computer="BOOTH-01", user="")
    closed = store.close_previous_windows_user_positions("booth-01", "new_user")
    assert len(closed) == 1 and closed[0]["agms"] == old.agms, closed
    assert store.get_active(old.agms) is None
    for p in (other_pc, same_user, unknown_user):
        assert store.get_active(p.agms) is not None, p.agms
    assert store.close_previous_windows_user_positions("BOOTH-01", "NEW_USER") == []
    assert store.close_previous_windows_user_positions("", "NEW_USER") == []
    assert store.close_previous_windows_user_positions("BOOTH-01", "") == []
    ends = [e for e in store.iter_all_events() if e.get("kind") == "END" and e.get("agms") == old.agms]
    assert len(ends) == 1, ends
    assert ends[0].get("end_reason") == "WINDOWS_USER_HANDOFF_RECOVERY", ends[0]
    assert ends[0]["start_event_id"] == a["event_id"]

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    officer, first, second = person(71999), person(71011), person(71012)
    store.start(first, "5", "ΕΙΣΟΔΟΣ")
    store.start(second, "6", "ΕΞΟΔΟΣ")
    store.start_officer_shift(officer)
    snapshot = {x["agms"]: x["event_id"] for x in store.active_all()}
    store.end(second)
    try:
        store.end_officer_shift(officer, expected_active_start_ids=snapshot)
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("The changed active list was accepted without re-confirmation")
    assert store.current_shift() is not None
    confirmed = {x["agms"]: x["event_id"] for x in store.active_all()}
    finalized = store.end_officer_shift(officer, expected_active_start_ids=confirmed)
    assert finalized["closed_active_agms"] == [first.agms], finalized
    assert not store.active_all()

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    officer, approved, excluded = person(72999), person(72001), person(72002)
    store.start(approved, "7", "ΕΙΣΟΔΟΣ")
    store.start(excluded, "8", "ΕΞΟΔΟΣ")
    store.start_officer_shift(officer)
    store.set_shift_member_state(excluded.agms, "EXCLUDED")
    snapshot = {approved.agms: store.get_active(approved.agms)["event_id"]}
    finalized = store.end_officer_shift(officer, expected_active_start_ids=snapshot)
    assert finalized["closed_active_agms"] == [approved.agms]
    assert store.get_active(approved.agms) is None
    assert store.get_active(excluded.agms) is not None
    assert any(
        e.get("kind") == "END" and e.get("agms") == approved.agms
        and e.get("end_reason") == "SHIFT_FINALIZED_BY_OFFICER"
        for e in store.iter_all_events()
    )

print("WINDOWS_USER_HANDOFF_REGRESSION: PASS (handoff, idempotence, non-target preservation, shift confirmation)")

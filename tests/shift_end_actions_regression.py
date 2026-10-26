from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def person(i):
    return MOD.PersonnelRecord(str(i), "ΑΣΤ", f"WORKER{i}", "TEST")


with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    officer, first, second, excluded = (person(i) for i in (8999, 8001, 8002, 8003))
    start_a = store.start(first, "1", "ΕΙΣΟΔΟΣ")
    start_b = store.start(second, "2", "ΕΙΣΟΔΟΣ")
    start_c = store.start(excluded, "3", "ΕΙΣΟΔΟΣ")
    shift = store.start_officer_shift(officer)
    shift_id = shift["shift_id"]
    store.set_shift_member_state(excluded.agms, "EXCLUDED")

    try:
        store.end_officer_shift_member(
            officer, first.agms, "INCORRECT_SHIFT", start_a["event_id"]
        )
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Wrong shift ID should never end a booth")
    assert store.get_active(first.agms) is not None

    try:
        store.end_officer_shift_member(
            officer, excluded.agms, shift_id, start_c["event_id"]
        )
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Excluded staff member was ended")
    assert store.get_active(excluded.agms) is not None

    result = store.end_officer_shift_member(officer, first.agms, shift_id, start_a["event_id"])
    assert result["end_reason"] == "SHIFT_SINGLE_BY_OFFICER"
    assert result["end_officer"]["agms"] == officer.agms
    assert store.get_active(first.agms) is None
    assert store.get_active(second.agms) is not None
    assert store.get_active(excluded.agms) is not None
    assert store.current_shift()["shift_id"] == shift_id

    for target in (first, second):
        try:
            store.end_officer_shift_member(officer, target.agms, shift_id, "WRONG_START")
        except MOD.BusyError:
            pass
        else:
            raise AssertionError("Wrong/old START ID should not be ended")
    assert store.get_active(second.agms) is not None

    # A new booth opening after officer preview must force a refresh.
    new_a = store.start(first, "4", "ΕΙΣΟΔΟΣ")
    try:
        store.end_officer_shift(
            officer, expected_shift_id=shift_id,
            expected_active_start_ids={second.agms: start_b["event_id"]},
        )
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Unconfirmed new START was included in a group END")
    assert store.get_active(first.agms)["event_id"] == new_a["event_id"]

    store.end_officer_shift_member(officer, first.agms, shift_id, new_a["event_id"])
    try:
        store.end_officer_shift(
            officer, expected_shift_id="INCORRECT_SHIFT",
            expected_active_start_ids={second.agms: start_b["event_id"]},
        )
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Wrong shift was finalized")

    finalized = store.end_officer_shift(
        officer, expected_shift_id=shift_id,
        expected_active_start_ids={second.agms: start_b["event_id"]},
    )
    assert finalized["status"] == "FINALIZED"
    assert finalized["closed_active_agms"] == [second.agms]
    assert store.get_active(second.agms) is None
    assert store.get_active(excluded.agms) is not None
    assert any(
        e["agms"] == second.agms
        and e.get("kind") == "END"
        and e.get("end_reason") == "SHIFT_FINALIZED_BY_OFFICER"
        and e.get("end_officer", {}).get("agms") == officer.agms
        for e in store.iter_all_events()
    )

# UI guard: the new modal must contain per-row and bulk actions, while
# the pre-existing live-map end control must remain in the same source.
import inspect
from position_tracking_ui_map import LiveMapDialog
from position_tracking_ui_shift_end import ShiftEndDialogMixin
source = (ROOT / "src" / "position_tracking.py").read_text(encoding="utf-8") + inspect.getsource(LiveMapDialog) + inspect.getsource(ShiftEndDialogMixin)
# Check actual button constructors, independent of whitespace/quote formatting
# introduced when a nested Qt class becomes an independent module.
import ast
labels = {n.args[0].value for n in ast.walk(ast.parse(source))
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id == 'QPushButton' and n.args
          and isinstance(n.args[0], ast.Constant)}
for required in ('ΛΗΞΗ', 'ΟΜΑΔΙΚΗ ΛΗΞΗ', 'ΟΛΟΚΛΗΡΩΣΗ ΒΑΡΔΙΑΣ', 'ΛΗΞΗ ΕΝΕΡΓΗΣ ΘΕΣΗΣ'):
    assert required in labels, required

print("SHIFT_END_ACTIONS_REGRESSION: PASS (single, group, stale start, wrong shift, excluded unaffected)")

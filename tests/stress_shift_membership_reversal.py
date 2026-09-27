from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "position_tracking.py"

spec = importlib.util.spec_from_file_location("position_tracking", SRC)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    personnel = tmp / "ΠΡΟΣΩΠΙΚΟ.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["ΑΓΜΣ", "ΒΑΘΜΟΣ", "ΕΠΩΝΥΜΟ", "ΟΝΟΜΑ"])
    ws.append(["9001", "ΑΝΘ/ΜΟΣ", "ΠΡΩΙΜΟΣ", "Α"])
    ws.append(["9002", "ΑΣΤ/ΚΑΣ", "ΥΣΤΕΡΟΣ", "Β"])
    ws.append(["9999", "ΑΞ/ΚΟΣ", "ΥΠΗΡΕΣΙΑΣ", "Γ"])
    wb.save(personnel)

    people = mod.PersonnelRepository.load(personnel)
    by = {p.agms: p for p in people}

    for cycle in range(100):
        root = tmp / f"runtime_{cycle:03d}"
        store = mod.SharedEventStore(root)

        shift_start = datetime(2026, 9, 27, 10, 0) + timedelta(days=cycle)
        early_start = shift_start - timedelta(minutes=17 + (cycle % 11))
        late_start = shift_start + timedelta(minutes=8 + (cycle % 13))
        shift_end = shift_start + timedelta(hours=8)

        # Ο 9001 δουλεύει ήδη πριν ξεκινήσει η βάρδια.
        store.start(by["9001"], "1", "ΕΙΣΟΔΟΣ", early_start)
        shift = store.start_officer_shift(
            by["9999"],
            shift_start,
            initial_approved=[],
            initial_excluded=["9001"],
        )
        assert "9001" in shift["excluded"]

        # Λάθος εξαίρεση -> αναίρεση -> ξανά εξαίρεση -> δεύτερη αναίρεση.
        for _ in range(3):
            shift = store.set_shift_member_state("9001", "APPROVED")
            restored = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "9001"]
            assert restored, f"cycle {cycle}: missing early restored session"
            assert restored[0]["start_dt"] == early_start, (cycle, restored[0]["start_dt"], early_start)
            shift = store.set_shift_member_state("9001", "EXCLUDED")
            assert "9001" in shift["excluded"]
        shift = store.set_shift_member_state("9001", "APPROVED")
        restored = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "9001"]
        assert restored and restored[0]["start_dt"] == early_start

        # Ο 9002 μπαίνει αργότερα, πάει pending, απορρίπτεται κατά λάθος και επανέρχεται.
        store.start(by["9002"], "2", "ΕΞΟΔΟΣ", late_start)
        shift = store.sync_active_shift()
        assert "9002" in shift["pending"]
        for _ in range(3):
            shift = store.set_shift_member_state("9002", "EXCLUDED")
            assert "9002" in shift["excluded"]
            shift = store.set_shift_member_state("9002", "APPROVED")
            restored_late = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "9002"]
            assert restored_late, f"cycle {cycle}: missing late restored session"
            assert restored_late[0]["start_dt"] == late_start, (cycle, restored_late[0]["start_dt"], late_start)

        final = store.end_officer_shift(by["9999"], shift_end)
        assert set(final["approved"]) == {"9001", "9002"}
        assert final["excluded"] == []
        sessions = store.shift_sessions_v2(final)
        by_agms = {}
        for item in sessions:
            by_agms.setdefault(item["start"].get("agms"), []).append(item)
        assert by_agms["9001"][0]["start_dt"] == early_start
        assert by_agms["9002"][0]["start_dt"] == late_start

print("SHIFT_MEMBERSHIP_REVERSAL_STRESS_100: PASS")

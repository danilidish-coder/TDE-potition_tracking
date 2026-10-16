from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime
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
    ws.append(["1001", "ΑΝΘ/ΜΟΣ", "ΑΛΦΑ", "ΑΝΔΡΕΑΣ"])
    ws.append(["1002", "ΑΡΧ/ΚΑΣ", "ΒΗΤΑ", "ΒΑΣΙΛΗΣ"])
    ws.append(["1003", "ΥΠΑΡΧ/ΚΑΣ", "ΓΑΜΑ", "ΓΕΩΡΓΙΟΣ"])
    ws.append(["1004", "ΑΣΤ/ΚΑΣ", "ΔΕΛΤΑ", "ΔΗΜΗΤΡΙΟΣ"])
    wb.save(personnel)

    people = mod.PersonnelRepository.load(personnel)
    assert len(people) == 4
    by = {p.agms: p for p in people}

    store = mod.SharedEventStore(tmp / ".tde_runtime")

    # Δύο ενεργοί πριν την έναρξη.
    store.start(by["1001"], "1", "ΕΙΣΟΔΟΣ", datetime(2026, 9, 26, 9, 55))
    store.start(by["1002"], "8", "ΕΞΟΔΟΣ", datetime(2026, 9, 26, 9, 57))

    # Προεπισκόπηση έναρξης: κρατάμε 1001, εξαιρούμε 1002.
    shift = store.start_officer_shift(
        by["1004"],
        datetime(2026, 9, 26, 10, 0),
        initial_approved=["1001"],
        initial_excluded=["1002"],
    )
    assert shift["approved"] == ["1001"]
    assert shift["excluded"] == ["1002"]
    assert shift["pending"] == []

    # Νέος εργαζόμενος μετά την έναρξη -> μία φορά σε pending.
    store.start(by["1003"], "2", "ΕΙΣΟΔΟΣ", datetime(2026, 9, 26, 10, 5))
    shift = store.sync_active_shift()
    assert shift["pending"] == ["1003"]
    shift2 = store.sync_active_shift()
    assert shift2["pending"] == ["1003"]

    # Νέος εργαζόμενος: λάθος εξαίρεση και μετά αναίρεση.
    shift = store.set_shift_member_state("1003", "EXCLUDED")
    assert "1003" in shift["excluded"]
    assert "1003" not in shift["pending"]
    shift = store.set_shift_member_state("1003", "APPROVED")
    assert "1003" in shift["approved"]
    assert "1003" not in shift["excluded"]
    late_restored = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "1003"]
    assert late_restored and late_restored[0]["start_dt"] == datetime(2026, 9, 26, 10, 5)

    # Διόρθωση λάθους: ο 1002 είχε ξεκινήσει ΠΡΙΝ τη βάρδια,
    # εξαιρέθηκε κατά λάθος και επανέρχεται σε ΑΠΟΔΟΧΗ.
    shift = store.set_shift_member_state("1002", "APPROVED")
    assert "1002" in shift["approved"]
    assert "1002" not in shift["excluded"]
    restored = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "1002"]
    assert restored, "Η αναίρεση εξαίρεσης πρέπει να επαναφέρει τη συνεδρία"
    assert restored[0]["start_dt"] == datetime(2026, 9, 26, 9, 57)

    # Επαναφορά ξανά σε ΕΞΑΙΡΕΣΗ και δεύτερη αναίρεση.
    shift = store.set_shift_member_state("1002", "EXCLUDED")
    assert "1002" in shift["excluded"]
    shift = store.set_shift_member_state("1002", "APPROVED")
    assert "1002" in shift["approved"]
    restored_again = [x for x in store.shift_sessions_v2(shift) if x["start"].get("agms") == "1002"]
    assert restored_again and restored_again[0]["start_dt"] == datetime(2026, 9, 26, 9, 57)

    # Λήξη βάρδιας: μόνο επιβεβαιωμένοι στη τελική λίστα.
    final = store.end_officer_shift(by["1004"], datetime(2026, 9, 26, 18, 0))
    assert final["status"] == "FINALIZED"
    assert set(final["approved"]) == {"1001", "1002", "1003"}
    assert final["excluded"] == []

    # UI markers: απλός αξ/υπ + κάτω κουμπιά + θέματα.
    import inspect
    from position_tracking_ui_view import MainViewMixin
    from position_tracking_ui_shift_end import ShiftEndDialogMixin
    from position_tracking_ui_shifts import ShiftControllerMixin
    source = SRC.read_text(encoding="utf-8") + inspect.getsource(MainViewMixin) + inspect.getsource(ShiftEndDialogMixin) + inspect.getsource(ShiftControllerMixin)
    for marker in (
        "ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ",
        "ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ",
        "ΛΗΞΗ ΒΑΡΔΙΑΣ",
        "ΠΡΟΕΠΙΣΚΟΠΗΣΗ ΕΝΑΡΞΗΣ ΒΑΡΔΙΑΣ",
        "ΕΠΙΒΕΒΑΙΩΣΗ ΛΗΞΗΣ ΒΑΡΔΙΑΣ",
        "ΕΠΙΛΟΓΗ ΛΙΣΤΑΣ ΠΡΟΣΩΠΙΚΟΥ",
        "ΕΝΕΡΓΕΣ ΘΕΣΕΙΣ ΕΡΓΑΣΙΑΣ",
        "ΦΩΤΕΙΝΟ",
        "ΣΚΟΤΕΙΝΟ",
        "Επιβεβαίωση εξαίρεσης",
        "Είστε βέβαιοι ότι θέλετε να ΕΞΑΙΡΕΣΕΤΕ",
    ):
        assert marker in source, marker

    assert "QGraphicsDropShadowEffect" not in source

print("OFFICER_SIMPLE_FLOW_SIMULATION: PASS")

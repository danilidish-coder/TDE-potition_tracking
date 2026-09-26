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

    # Επιβεβαίωση νέου εργαζόμενου.
    shift = store.set_shift_member_state("1003", "APPROVED")
    assert "1003" in shift["approved"]
    assert "1003" not in shift["pending"]

    # Λήξη βάρδιας: μόνο επιβεβαιωμένοι στη τελική λίστα.
    final = store.end_officer_shift(by["1004"], datetime(2026, 9, 26, 18, 0))
    assert final["status"] == "FINALIZED"
    assert set(final["approved"]) == {"1001", "1003"}
    assert final["excluded"] == ["1002"]

    # UI markers: απλός αξ/υπ + κάτω κουμπιά + θέματα.
    source = SRC.read_text(encoding="utf-8")
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
    ):
        assert marker in source, marker

    assert "QGraphicsDropShadowEffect" not in source

print("OFFICER_SIMPLE_FLOW_SIMULATION: PASS")

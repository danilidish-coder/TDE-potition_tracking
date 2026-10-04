from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

app = QApplication.instance() or QApplication([])

shift = {
    "version": 2,
    "shift_id": "SHIFT_20261004_100000",
    "status": "FINALIZED",
    "start_at": "2026-10-04T10:00:00",
    "end_at": "2026-10-04T18:00:00",
    "approved": [],
    "start_officer": {
        "agms": "123456",
        "rank": "ΑΝΘ/ΜΟΣ",
        "surname": "ΔΟΚΙΜΗ",
        "given_name": "ΑΞΙΩΜΑΤΙΚΟΣ",
        "full_name": "ΔΟΚΙΜΗ ΑΞΙΩΜΑΤΙΚΟΣ",
    },
}

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))

    current = MOD.create_shift_pdf(store, shift, {})
    assert current.is_file(), current
    assert current.suffix.lower() == ".pdf", current
    assert current.read_bytes()[:4] == b"%PDF", "Current report is not a PDF"

    archived = MOD.archive_shift_pdf(store, shift, {})
    assert archived.is_file(), archived
    assert archived.suffix.lower() == ".pdf", archived
    assert archived.read_bytes()[:4] == b"%PDF", "Archived report is not a PDF"
    assert "2026" in archived.parts and "10" in archived.parts and "2026-10-04" in archived.parts

print("PDF_REPORT_REGRESSION: PASS")

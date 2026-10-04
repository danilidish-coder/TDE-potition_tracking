from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
import sys
import tempfile
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

    preview = MOD.create_shift_pdf(store, shift, {})
    assert preview.is_file(), preview
    assert preview.suffix.lower() == ".pdf", preview
    assert preview.read_bytes()[:4] == b"%PDF", "Preview is not a PDF"
    assert str(store.root) not in str(preview), "On-demand PDF must not be stored in TDE_DATA"

    alias_preview = MOD.archive_shift_pdf(store, shift, {})
    assert alias_preview == preview, (alias_preview, preview)
    assert not list(store.archive.rglob("*.pdf")), "Archive must not accumulate permanent PDFs"

print("PDF_REPORT_REGRESSION: PASS")

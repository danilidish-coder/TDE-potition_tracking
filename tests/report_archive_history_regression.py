from __future__ import annotations

import importlib.util
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MOD)

shift = {
    "shift_id": "SHIFT_20261001_100000",
    "status": "FINALIZED",
    "start_at": "2026-10-01T10:00:00",
    "end_at": "2026-10-02T10:00:00",
    "approved": [],
    "start_officer": {
        "agms": "123456",
        "rank": "ΑΝΘ/ΜΟΣ",
        "surname": "ΚΛΙΑΝΗΣ",
        "given_name": "ΧΡΗΣΤΟΣ",
        "full_name": "ΚΛΙΑΝΗΣ ΧΡΗΣΤΟΣ",
    },
}

title = MOD.shift_report_title(shift)
assert title == "Αναφορά 01-02 Οκτωβρίου 2026 - ΚΛΙΑΝΗΣ ΧΡΗΣΤΟΣ", title

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    path = MOD.archive_shift_docx(store, shift, {})
    assert path.is_file(), path
    assert path.name == title + ".docx", path.name
    assert "2026" in path.parts and "10" in path.parts and "2026-10-02" in path.parts

print("REPORT_ARCHIVE_HISTORY_REGRESSION: PASS")

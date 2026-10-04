from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

legacy_shift = {
    "version": 2,
    "shift_id": "SHIFT_20261003_100000_000001",
    "status": "FINALIZED",
    "start_at": "2026-10-03T10:00:00",
    "end_at": "2026-10-04T10:00:00",
    "approved": ["111111"],
    "excluded": [],
    "pending": [],
    "start_officer": {
        "agms": "999999",
        "rank": "ΑΝΘ/ΜΟΣ",
        "surname": "ΠΑΛΙΑ",
        "given_name": "ΒΑΡΔΙΑ",
        "full_name": "ΠΑΛΙΑ ΒΑΡΔΙΑ",
    },
}

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "TDE_DATA"
    shifts = root / "shifts"
    shifts.mkdir(parents=True, exist_ok=True)
    legacy_path = shifts / f"{legacy_shift['shift_id']}.json"
    legacy_path.write_text(json.dumps(legacy_shift, ensure_ascii=False), encoding="utf-8")
    (shifts / "CURRENT_SHIFT.json").write_text(json.dumps(legacy_shift, ensure_ascii=False), encoding="utf-8")

    store = MOD.SharedEventStore(root)

    assert store.shift_db.is_file(), store.shift_db
    imported = store.get_shift(legacy_shift["shift_id"])
    assert imported is not None
    assert imported["status"] == "FINALIZED"

    listed = store.list_shifts()
    assert any(s.get("shift_id") == legacy_shift["shift_id"] for s in listed)

    current = store.current_report_shift()
    assert current is not None
    assert current["shift_id"] == legacy_shift["shift_id"]

    with sqlite3.connect(store.shift_db) as con:
        count = con.execute("SELECT COUNT(*) FROM shifts WHERE shift_id=?", (legacy_shift["shift_id"],)).fetchone()[0]
    assert count == 1

print("SQLITE_SHIFT_ARCHIVE_REGRESSION: PASS")

from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

officer = MOD.PersonnelRecord(
    agms="123456",
    rank="ΑΝΘ/ΜΟΣ",
    surname="ΔΟΚΙΜΗ",
    given_name="ΑΞΙΩΜΑΤΙΚΟΣ",
)

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))

    first = store.start_officer_shift(officer, when=datetime(2026, 10, 4, 10, 0, 0))
    first_id = first["shift_id"]
    ended = store.end_officer_shift(officer, when=datetime(2026, 10, 4, 18, 0, 0))

    assert ended["status"] == "FINALIZED"
    assert store.current_shift() is None, "Finalized shift must not remain operationally active"

    current_report = store.current_report_shift()
    assert current_report is not None, "Ended shift must remain available as current report"
    assert current_report["shift_id"] == first_id
    assert current_report["status"] == "FINALIZED"
    assert current_report["end_at"] == "2026-10-04T18:00:00"

    archived_ids = {s.get("shift_id") for s in store.list_shifts()}
    assert first_id in archived_ids, "Ended shift must still be present in shift archive"

    second = store.start_officer_shift(officer, when=datetime(2026, 10, 5, 10, 0, 0))
    assert second["shift_id"] != first_id

    current_report = store.current_report_shift()
    assert current_report is not None
    assert current_report["shift_id"] == second["shift_id"], "Current report must switch only when next shift starts"
    assert current_report["status"] == "ACTIVE"

print("CURRENT_REPORT_RETENTION_REGRESSION: PASS")

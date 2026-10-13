from __future__ import annotations

import importlib.util
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

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    admin = MOD.PersonnelRecord("900", "ΑΝΘ/ΜΟΣ", "ΑΞΥΠ", "TEST")
    first = MOD.PersonnelRecord("101", "ΑΣΤ", "FIRST", "TEST")
    excluded = MOD.PersonnelRecord("102", "ΑΣΤ", "SECOND", "TEST")
    base = datetime.now().replace(microsecond=0) - timedelta(hours=2)
    store.start(first, "1", "ΕΙΣΟΔΟΣ", when=base)
    store.start(excluded, "2", "ΕΞΟΔΟΣ", when=base)
    shift = store.start_officer_shift(
        admin, when=base + timedelta(minutes=1),
        initial_approved=[first.agms], initial_excluded=[excluded.agms],
    )
    assert store.get_active(first.agms) is not None
    ended = store.end_officer_shift(admin, when=base + timedelta(hours=1))
    assert ended["status"] == "FINALIZED"
    assert ended["closed_active_agms"] == [first.agms]
    assert store.get_active(first.agms) is None
    assert store.get_active(excluded.agms) is not None
    rows = store.search_personnel_sessions()
    assert any(row["agms"] == first.agms for row in rows)
    store.start(first, "1", "ΕΙΣΟΔΟΣ", when=base + timedelta(hours=1, minutes=1))
    assert store.get_active(first.agms) is not None

print("SHIFT_END_RELEASE_REGRESSION: PASS")

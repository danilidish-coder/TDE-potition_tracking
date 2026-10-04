from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    base = datetime(2026, 9, 1, 10, 0, 0)

    for i in range(25):
        start = base + timedelta(days=i)
        end = start + timedelta(hours=12)
        surname = "ΔΑΝΙΗΛΙΔΗΣ" if i in {5, 15, 24} else "ΔΟΚΙΜΗ"
        shift = {
            "version": 2,
            "shift_id": f"SHIFT_{start:%Y%m%d_%H%M%S}",
            "status": "FINALIZED",
            "start_at": start.isoformat(timespec="seconds"),
            "end_at": end.isoformat(timespec="seconds"),
            "approved": [],
            "excluded": [],
            "pending": [],
            "start_officer": {
                "agms": f"{900000+i}",
                "rank": "ΑΝΘ/ΜΟΣ",
                "surname": surname,
                "given_name": f"ΑΞΙΩΜΑΤΙΚΟΣ{i}",
                "full_name": f"{surname} ΑΞΙΩΜΑΤΙΚΟΣ{i}",
            },
        }
        store._store_shift_snapshot(shift)

    recent = store.search_finalized_shifts(limit=20)
    assert len(recent) == 20
    assert recent[0]["start_at"].startswith("2026-09-25")
    assert recent[-1]["start_at"].startswith("2026-09-06")

    ranged = store.search_finalized_shifts(
        date_from=date(2026, 9, 10),
        date_to=date(2026, 9, 12),
    )
    assert [s["start_at"][:10] for s in ranged] == [
        "2026-09-12", "2026-09-11", "2026-09-10"
    ]

    officer = store.search_finalized_shifts(officer_query="δανιηλιδης")
    assert len(officer) == 3
    assert all((s.get("start_officer") or {}).get("surname") == "ΔΑΝΙΗΛΙΔΗΣ" for s in officer)

    officer_agms = store.search_finalized_shifts(officer_query="900024")
    assert len(officer_agms) == 1
    assert officer_agms[0]["start_at"].startswith("2026-09-25")

print("REPORT_ARCHIVE_SEARCH_REGRESSION: PASS")

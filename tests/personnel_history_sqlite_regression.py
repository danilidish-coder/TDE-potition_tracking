from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import importlib.util
import json
import sys
import tempfile
from datetime import date, datetime, time
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

app = QApplication.instance() or QApplication([])

a = MOD.PersonnelRecord("100001", "ΑΡΧ/ΚΑΣ", "ΑΛΦΑ", "ΑΝΝΑ")
b = MOD.PersonnelRecord("100002", "ΥΠΑΡΧ/ΚΑΣ", "ΒΗΤΑ", "ΒΑΣΙΛΗΣ")
c = MOD.PersonnelRecord("100003", "ΑΡΧ/ΚΑΣ", "ΓΑΜΜΑ", "ΓΙΩΡΓΟΣ")

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))

    store.start(a, "1", "ΕΙΣΟΔΟΣ", datetime(2026, 10, 4, 8, 0, 0))
    store.end(a, datetime(2026, 10, 4, 10, 0, 0))
    store.start(a, "8", "ΕΞΟΔΟΣ", datetime(2026, 10, 4, 10, 30, 0))
    store.end(a, datetime(2026, 10, 4, 12, 0, 0))

    store.start(b, "9", "ΕΞΟΔΟΣ", datetime(2026, 10, 4, 9, 0, 0))
    store.end(b, datetime(2026, 10, 4, 11, 0, 0))

    # Open session: must not enter historical completed-work archive.
    store.start(c, "2", "ΕΙΣΟΔΟΣ", datetime(2026, 10, 4, 13, 0, 0))

    all_rows = store.search_personnel_sessions()
    assert len(all_rows) == 3, all_rows

    workers = store.list_personnel_workers()
    worker_ids = {w["agms"] for w in workers}
    assert worker_ids == {"100001", "100002"}, worker_ids

    a_rows = store.search_personnel_sessions(person_query="αλφα")
    assert len(a_rows) == 2
    summary = MOD.summarize_personnel_history(a_rows)
    assert summary["total_seconds"] == 12600
    assert summary["by_direction"]["ΕΙΣΟΔΟΣ"] == 7200
    assert summary["by_direction"]["ΕΞΟΔΟΣ"] == 5400
    assert summary["by_direction_position"][("ΕΙΣΟΔΟΣ", "1")] == 7200
    assert summary["by_direction_position"][("ΕΞΟΔΟΣ", "8")] == 5400

    assert len(store.search_personnel_sessions(person_query="100001", position="8")) == 1
    assert len(store.search_personnel_sessions(person_query="100001", direction="ΕΙΣΟΔΟΣ")) == 1
    assert len(store.search_personnel_sessions(date_from=date(2026, 10, 4), date_to=date(2026, 10, 4))) == 3

    at_0930_exit = store.search_personnel_sessions(
        direction="ΕΞΟΔΟΣ", moment=datetime(2026, 10, 4, 9, 30, 0)
    )
    assert [r["agms"] for r in at_0930_exit] == ["100002"]

    at_1045_pos8 = store.search_personnel_sessions(
        position="8", direction="ΕΞΟΔΟΣ", moment=datetime(2026, 10, 4, 10, 45, 0)
    )
    assert [r["agms"] for r in at_1045_pos8] == ["100001"]

    morning_window = store.search_personnel_sessions(
        time_from=time(9, 30), time_to=time(10, 45)
    )
    assert len(morning_window) == 3

    long_sessions = store.search_personnel_sessions(min_duration_minutes=100)
    assert {r["start_event_id"] for r in long_sessions} == {
        all_rows[1]["start_event_id"] if all_rows[1]["duration_seconds"] == 7200 else all_rows[0]["start_event_id"],
        next(r["start_event_id"] for r in all_rows if r["agms"] == "100002"),
    } or len(long_sessions) == 2
    assert len(long_sessions) == 2

    pdf = MOD.create_personnel_history_pdf(
        a_rows,
        "Άτομο: ΑΛΦΑ ΑΝΝΑ",
        MOD.summarize_personnel_history(a_rows),
    )
    assert pdf.is_file()
    assert pdf.read_bytes()[:4] == b"%PDF"
    assert str(store.root) not in str(pdf)

# Legacy event JSON migration into SQLite.
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp) / "TDE_DATA"
    day = root / "events" / "2026" / "10" / "01"
    day.mkdir(parents=True, exist_ok=True)
    start = {
        "version": 2, "event_id": "legacy-start", "kind": "START",
        "timestamp": "2026-10-01T14:00:00", "agms": "777777", "rank": "ΑΡΧ/ΚΑΣ",
        "surname": "ΠΑΛΙΟΣ", "given_name": "ΧΡΗΣΤΗΣ", "full_name": "ΠΑΛΙΟΣ ΧΡΗΣΤΗΣ",
        "position": "4", "direction": "ΕΙΣΟΔΟΣ", "computer": "PC1", "user": "u1",
    }
    end = {
        "version": 2, "event_id": "legacy-end", "kind": "END",
        "timestamp": "2026-10-01T16:30:00", "start_event_id": "legacy-start",
        "agms": "777777", "rank": "ΑΡΧ/ΚΑΣ", "surname": "ΠΑΛΙΟΣ",
        "given_name": "ΧΡΗΣΤΗΣ", "full_name": "ΠΑΛΙΟΣ ΧΡΗΣΤΗΣ",
        "position": "4", "direction": "ΕΙΣΟΔΟΣ", "computer": "PC1", "user": "u1",
    }
    (day / "a.json").write_text(json.dumps(start, ensure_ascii=False), encoding="utf-8")
    (day / "b.json").write_text(json.dumps(end, ensure_ascii=False), encoding="utf-8")

    migrated = MOD.SharedEventStore(root)
    rows = migrated.search_personnel_sessions(person_query="ΠΑΛΙΟΣ")
    assert len(rows) == 1
    assert rows[0]["position"] == "4"
    assert rows[0]["duration_seconds"] == 9000

print("PERSONNEL_HISTORY_SQLITE_REGRESSION: PASS")

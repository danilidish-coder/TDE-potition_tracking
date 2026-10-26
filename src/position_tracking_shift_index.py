"""Shift SQLite schema, snapshot persistence and current-report index."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
from position_tracking_common import _clean


class ShiftIndexMixin:
    @staticmethod
    def _upsert_shift_con(con, shift: dict):
        shift_id = _clean(shift.get("shift_id"))
        if not shift_id:
            raise ValueError("Μη έγκυρη βάρδια.")
        status = _clean(shift.get("status")).upper() or "DRAFT"
        start_at = _clean(shift.get("start_at"))
        end_at = _clean(shift.get("end_at")) or None
        payload = json.dumps(shift, ensure_ascii=False, separators=(",", ":"))
        con.execute(
            """
            INSERT INTO shifts (shift_id, status, start_at, end_at, data_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(shift_id) DO UPDATE SET
                status=excluded.status,
                start_at=excluded.start_at,
                end_at=excluded.end_at,
                data_json=excluded.data_json,
                updated_at=excluded.updated_at
            """,
            (shift_id, status, start_at, end_at, payload, datetime.now().isoformat(timespec="seconds")),
        )


    def _init_shift_db(self):
        self.shift_db.parent.mkdir(parents=True, exist_ok=True)
        with self._shift_db_write_lock():
            with self._shift_db_connect() as con:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS shifts (
                        shift_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        start_at TEXT NOT NULL,
                        end_at TEXT,
                        data_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_shifts_start_at ON shifts(start_at DESC)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status)")
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS meta (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                    """
                )
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS personnel_sessions (
                        session_id TEXT PRIMARY KEY,
                        start_event_id TEXT UNIQUE NOT NULL,
                        end_event_id TEXT NOT NULL,
                        agms TEXT NOT NULL,
                        rank TEXT,
                        surname TEXT,
                        given_name TEXT,
                        full_name TEXT,
                        person_search TEXT NOT NULL,
                        position TEXT NOT NULL,
                        direction TEXT NOT NULL,
                        start_at TEXT NOT NULL,
                        end_at TEXT NOT NULL,
                        duration_seconds INTEGER NOT NULL,
                        start_computer TEXT,
                        start_user TEXT,
                        end_computer TEXT,
                        end_user TEXT
                    )
                    """
                )
                con.execute("CREATE INDEX IF NOT EXISTS idx_personnel_sessions_start ON personnel_sessions(start_at DESC)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_personnel_sessions_end ON personnel_sessions(end_at DESC)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_personnel_sessions_person ON personnel_sessions(person_search)")
                con.execute("CREATE INDEX IF NOT EXISTS idx_personnel_sessions_position ON personnel_sessions(position, direction)")
                migrated = con.execute(
                    "SELECT value FROM meta WHERE key='legacy_shift_json_migrated_v1'"
                ).fetchone()
                if not migrated:
                    newest = None
                    for path in sorted(self.shifts.glob("SHIFT_*.json")):
                        try:
                            data = json.loads(path.read_text(encoding="utf-8"))
                            if _clean(data.get("shift_id")):
                                self._upsert_shift_con(con, data)
                                newest = data
                        except Exception:
                            continue
                    current_path = self._current_shift_path()
                    try:
                        current = json.loads(current_path.read_text(encoding="utf-8"))
                        if _clean(current.get("shift_id")):
                            self._upsert_shift_con(con, current)
                            newest = current
                    except Exception:
                        pass
                    if newest and _clean(newest.get("shift_id")):
                        con.execute(
                            "INSERT OR REPLACE INTO meta(key,value) VALUES('current_report_shift_id',?)",
                            (_clean(newest.get("shift_id")),),
                        )
                    con.execute(
                        "INSERT OR REPLACE INTO meta(key,value) VALUES('legacy_shift_json_migrated_v1','1')"
                    )

                personnel_migrated = con.execute(
                    "SELECT value FROM meta WHERE key='legacy_personnel_sessions_migrated_v1'"
                ).fetchone()
                if not personnel_migrated:
                    starts: dict[str, dict] = {}
                    for event in self.iter_all_events():
                        kind = _clean(event.get("kind")).upper()
                        if kind == "START":
                            starts[_clean(event.get("event_id"))] = event
                        elif kind == "END":
                            start = starts.get(_clean(event.get("start_event_id")))
                            if start:
                                self._upsert_personnel_session_con(con, start, event)
                    con.execute(
                        "INSERT OR REPLACE INTO meta(key,value) VALUES('legacy_personnel_sessions_migrated_v1','1')"
                    )


    def _store_shift_snapshot(self, shift: dict, make_current_report: bool = False):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as con:
                self._upsert_shift_con(con, shift)
                if make_current_report:
                    con.execute(
                        "INSERT OR REPLACE INTO meta(key,value) VALUES('current_report_shift_id',?)",
                        (_clean(shift.get("shift_id")),),
                    )


    def get_shift(self, shift_id: str) -> dict | None:
        shift_id = _clean(shift_id)
        if not shift_id:
            return None
        try:
            with self._shift_db_connect() as con:
                row = con.execute("SELECT data_json FROM shifts WHERE shift_id=?", (shift_id,)).fetchone()
            return json.loads(row["data_json"]) if row else None
        except Exception:
            return None


    def _current_report_shift_id(self) -> str:
        try:
            with self._shift_db_connect() as con:
                row = con.execute("SELECT value FROM meta WHERE key='current_report_shift_id'").fetchone()
            return _clean(row["value"]) if row else ""
        except Exception:
            return ""


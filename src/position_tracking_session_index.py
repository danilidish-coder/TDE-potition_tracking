"""Durable personnel session index, pending reconciliation and history search."""
from __future__ import annotations
from datetime import date, datetime, timedelta, time as dtime
from pathlib import Path
import json
import sqlite3
from position_tracking_common import _clean, _safe_name, _norm_search
from position_tracking_store_io import BusyError


class SessionIndexMixin:
    @staticmethod
    def _upsert_personnel_session_con(con, start: dict, end: dict):
        start_event_id = _clean(start.get("event_id"))
        end_event_id = _clean(end.get("event_id"))
        if not start_event_id or not end_event_id:
            return
        try:
            start_dt = datetime.fromisoformat(_clean(start.get("timestamp")))
            end_dt = datetime.fromisoformat(_clean(end.get("timestamp")))
        except Exception:
            return
        if end_dt < start_dt:
            return
        agms = _clean(start.get("agms") or end.get("agms"))
        rank = _clean(start.get("rank") or end.get("rank"))
        surname = _clean(start.get("surname") or end.get("surname"))
        given_name = _clean(start.get("given_name") or end.get("given_name"))
        full_name = _clean(start.get("full_name") or end.get("full_name") or f"{surname} {given_name}")
        person_search = _norm_search(f"{agms} {rank} {surname} {given_name} {full_name}")
        duration_seconds = max(0, int((end_dt - start_dt).total_seconds()))
        con.execute(
            """
            INSERT INTO personnel_sessions (
                session_id, start_event_id, end_event_id, agms, rank, surname, given_name,
                full_name, person_search, position, direction, start_at, end_at,
                duration_seconds, start_computer, start_user, end_computer, end_user
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(start_event_id) DO UPDATE SET
                end_event_id=excluded.end_event_id,
                agms=excluded.agms,
                rank=excluded.rank,
                surname=excluded.surname,
                given_name=excluded.given_name,
                full_name=excluded.full_name,
                person_search=excluded.person_search,
                position=excluded.position,
                direction=excluded.direction,
                start_at=excluded.start_at,
                end_at=excluded.end_at,
                duration_seconds=excluded.duration_seconds,
                start_computer=excluded.start_computer,
                start_user=excluded.start_user,
                end_computer=excluded.end_computer,
                end_user=excluded.end_user
            """,
            (
                start_event_id, start_event_id, end_event_id, agms, rank, surname, given_name,
                full_name, person_search, _clean(start.get("position")),
                _clean(start.get("direction")).upper(),
                start_dt.isoformat(timespec="seconds"), end_dt.isoformat(timespec="seconds"),
                duration_seconds, _clean(start.get("computer")), _clean(start.get("user")),
                _clean(end.get("computer")), _clean(end.get("user")),
            ),
        )


    def _store_personnel_session(self, start: dict, end: dict):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as con:
                self._upsert_personnel_session_con(con, start, end)


    def _has_end_receipt(self, active: dict) -> bool:
        start_id = _safe_name(active.get("event_id"))
        receipt = self.pending_index / f"{start_id}.json"
        if not receipt.is_file():
            return False
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            return _clean(data.get("start", {}).get("event_id")) == _clean(active.get("event_id"))
        except Exception as exc:
            raise BusyError(f"Αδύνατος έλεγχος προσωρινής λήξης {start_id}: {exc}") from exc


    def reconcile_pending_sessions(self) -> int:
        """Recover committed END events after a crash, without dropping history."""
        done = 0
        for path in sorted(self.pending_index.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            start, end = data["start"], data["end"]
            agms = _clean(start.get("agms"))
            with self.officer_lock(agms):
                active_path = self._active_path(agms)
                if active_path.is_file():
                    current = json.loads(active_path.read_text(encoding="utf-8"))
                    if _clean(current.get("event_id")) == _clean(start.get("event_id")):
                        active_path.unlink()
                self._store_personnel_session(start, end)
                path.unlink(missing_ok=True)
                done += 1
        return done


    @staticmethod
    def _session_row_dict(row) -> dict:
        return {
            "session_id": _clean(row["session_id"]),
            "start_event_id": _clean(row["start_event_id"]),
            "end_event_id": _clean(row["end_event_id"]),
            "agms": _clean(row["agms"]),
            "rank": _clean(row["rank"]),
            "surname": _clean(row["surname"]),
            "given_name": _clean(row["given_name"]),
            "full_name": _clean(row["full_name"]),
            "position": _clean(row["position"]),
            "direction": _clean(row["direction"]).upper(),
            "start_at": _clean(row["start_at"]),
            "end_at": _clean(row["end_at"]),
            "duration_seconds": int(row["duration_seconds"] or 0),
        }


    @staticmethod
    def _session_overlaps_clock_window(start_dt: datetime, end_dt: datetime, time_from: dtime, time_to: dtime) -> bool:
        day = start_dt.date() - timedelta(days=1)
        last = end_dt.date()
        while day <= last:
            window_start = datetime.combine(day, time_from)
            window_end = datetime.combine(day, time_to)
            if time_to <= time_from:
                window_end += timedelta(days=1)
            if start_dt < window_end and end_dt > window_start:
                return True
            day += timedelta(days=1)
        return False


    def search_personnel_sessions(
        self,
        person_query: str = "",
        date_from: date | None = None,
        date_to: date | None = None,
        position: str = "",
        direction: str = "",
        time_from: dtime | None = None,
        time_to: dtime | None = None,
        moment: datetime | None = None,
        min_duration_minutes: int = 0,
        max_duration_minutes: int = 0,
        limit: int | None = None,
    ) -> list[dict]:
        clauses = ["1=1"]
        params: list[object] = []
        query = _norm_search(person_query)
        if query:
            clauses.append("person_search LIKE ?")
            params.append(f"%{query}%")
        if date_from is not None:
            clauses.append("end_at>=?")
            params.append(f"{date_from:%Y-%m-%d}T00:00:00")
        if date_to is not None:
            clauses.append("start_at<=?")
            params.append(f"{date_to:%Y-%m-%d}T23:59:59")
        position = _clean(position)
        if position and position != "ΟΛΕΣ":
            clauses.append("position=?")
            params.append(position)
        direction = _clean(direction).upper()
        if direction and direction != "ΟΛΑ":
            clauses.append("direction=?")
            params.append(direction)
        if moment is not None:
            stamp = moment.isoformat(timespec="seconds")
            clauses.append("start_at<=?")
            clauses.append("end_at>?")
            params.extend([stamp, stamp])
        if int(min_duration_minutes or 0) > 0:
            clauses.append("duration_seconds>=?")
            params.append(int(min_duration_minutes) * 60)
        if int(max_duration_minutes or 0) > 0:
            clauses.append("duration_seconds<=?")
            params.append(int(max_duration_minutes) * 60)

        sql = "SELECT * FROM personnel_sessions WHERE " + " AND ".join(clauses) + " ORDER BY start_at DESC"
        if limit is not None and int(limit) > 0 and time_from is None and time_to is None:
            sql += " LIMIT ?"
            params.append(int(limit))

        rows: list[dict] = []
        try:
            with self._shift_db_connect() as con:
                db_rows = con.execute(sql, params).fetchall()
            for row in db_rows:
                item = self._session_row_dict(row)
                if time_from is not None and time_to is not None:
                    try:
                        sdt = datetime.fromisoformat(item["start_at"])
                        edt = datetime.fromisoformat(item["end_at"])
                    except Exception:
                        continue
                    if not self._session_overlaps_clock_window(sdt, edt, time_from, time_to):
                        continue
                rows.append(item)
                if limit is not None and int(limit) > 0 and len(rows) >= int(limit):
                    break
        except Exception:
            return []
        return rows


    def list_personnel_workers(self) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        try:
            with self._shift_db_connect() as con:
                rows = con.execute(
                    """
                    SELECT agms, rank, surname, given_name, full_name
                    FROM personnel_sessions
                    ORDER BY start_at DESC
                    """
                ).fetchall()
            for row in rows:
                agms = _clean(row["agms"])
                if not agms or agms in seen:
                    continue
                seen.add(agms)
                result.append({
                    "agms": agms,
                    "rank": _clean(row["rank"]),
                    "surname": _clean(row["surname"]),
                    "given_name": _clean(row["given_name"]),
                    "full_name": _clean(row["full_name"]),
                })
        except Exception:
            return []
        return sorted(result, key=lambda x: (_norm_search(x.get("surname")), _norm_search(x.get("given_name")), x.get("agms", "")))


    def list_session_positions(self) -> list[str]:
        try:
            with self._shift_db_connect() as con:
                rows = con.execute(
                    "SELECT DISTINCT position FROM personnel_sessions WHERE position<>'' ORDER BY position"
                ).fetchall()
            return [_clean(row["position"]) for row in rows if _clean(row["position"])]
        except Exception:
            return []


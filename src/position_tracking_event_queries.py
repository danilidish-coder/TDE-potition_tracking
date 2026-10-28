"""Event/session projection, roster windows and finalized-shift queries."""
from __future__ import annotations
from datetime import date, datetime, timedelta, time as dtime
import json
import unicodedata
from position_tracking_common import _clean
from position_tracking_settings import DEFAULT_CUTOFF


class EventQueryMixin:
    def iter_events(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        states = self._event_states()
        result: list[dict] = []
        current = start_dt.date()
        last = end_dt.date()
        while current <= last:
            folder = self.events / f"{current:%Y}" / f"{current:%m}" / f"{current:%Y-%m-%d}"
            if folder.exists():
                for path in sorted(folder.glob("*.json")):
                    try:
                        e = self._apply_start_correction(json.loads(path.read_text(encoding="utf-8")))
                        if states is not None and states.get(e.get("event_id")) != "COMMITTED":
                            continue
                        ts = datetime.fromisoformat(e.get("timestamp", ""))
                        if start_dt <= ts < end_dt:
                            result.append(e)
                    except Exception:
                        pass
            current += timedelta(days=1)
        known = {event['event_id'] for event in result}
        result.extend(event for event in self._handover_events() if event['event_id'] not in known
                      and start_dt <= datetime.fromisoformat(event['timestamp']) < end_dt)
        return sorted(result, key=lambda e: (e.get("timestamp", ""), e.get('kind') == 'START'))


    def iter_all_events(self) -> list[dict]:
        states = self._event_states()
        result: list[dict] = []
        if not self.events.exists():
            return result
        for path in sorted(self.events.rglob("*.json")):
            try:
                event = self._apply_start_correction(json.loads(path.read_text(encoding="utf-8")))
                if states is not None and states.get(event.get("event_id")) != "COMMITTED":
                    continue
                if _clean(event.get("timestamp")):
                    result.append(event)
            except Exception:
                pass
        known = {event['event_id'] for event in result}
        result.extend(event for event in self._handover_events() if event['event_id'] not in known)
        return sorted(result, key=lambda e: (_clean(e.get("timestamp")), e.get('kind') == 'START'))


    def completed_sessions_all(self) -> list[dict]:
        sessions: list[dict] = []
        for row in reversed(self.search_personnel_sessions()):
            try:
                start_dt = datetime.fromisoformat(row["start_at"])
                end_dt = datetime.fromisoformat(row["end_at"])
            except Exception:
                continue
            start = {
                "event_id": row["start_event_id"], "kind": "START", "timestamp": row["start_at"],
                "agms": row["agms"], "rank": row["rank"], "surname": row["surname"],
                "given_name": row["given_name"], "full_name": row["full_name"],
                "position": row["position"], "direction": row["direction"],
            }
            end = {
                "event_id": row["end_event_id"], "kind": "END", "timestamp": row["end_at"],
                "start_event_id": row["start_event_id"], "agms": row["agms"],
                "rank": row["rank"], "surname": row["surname"], "given_name": row["given_name"],
                "full_name": row["full_name"], "position": row["position"], "direction": row["direction"],
            }
            sessions.append({"start": start, "end": end, "start_dt": start_dt, "end_dt": end_dt})
        return sessions


    def shift_sessions_v2(self, shift: dict) -> list[dict]:
        approved = {_clean(x) for x in shift.get("approved", []) if _clean(x)}
        if not approved:
            return []
        start_at = datetime.fromisoformat(shift["start_at"])
        end_at = datetime.fromisoformat(shift.get("end_at") or datetime.now().isoformat(timespec="seconds"))
        initial = {a: dict(item) for a, item in (shift.get("initial_active", {}) or {}).items()}
        for info in initial.values():
            if _clean(info.get("event_id")):
                info["timestamp"] = self._effective_start_timestamp(
                    _clean(info["event_id"]), _clean(info.get("timestamp"))
                )
        search_start = start_at
        for agms in approved:
            try:
                ts = datetime.fromisoformat(_clean((initial.get(agms) or {}).get("timestamp")))
                if ts < search_start:
                    search_start = ts
            except Exception:
                pass
        events = self.iter_events(search_start, end_at + timedelta(seconds=1))
        starts: dict[str, dict] = {_clean(e.get("event_id")): e for e in events if e.get("kind") == "START"}
        sessions: list[dict] = []
        for e in events:
            agms = _clean(e.get("agms"))
            if agms not in approved:
                continue
            if e.get("kind") == "START":
                starts[_clean(e.get("event_id"))] = e
            elif e.get("kind") == "END":
                st = starts.get(_clean(e.get("start_event_id")))
                if not st:
                    continue
                sdt = datetime.fromisoformat(st["timestamp"]); edt = datetime.fromisoformat(e["timestamp"])
                threshold = start_at
                try:
                    threshold = datetime.fromisoformat(_clean((initial.get(agms) or {}).get("timestamp")))
                except Exception:
                    pass
                if sdt >= threshold and sdt < end_at:
                    sessions.append({"start": st, "end": e, "start_dt": sdt, "end_dt": min(edt, end_at)})
        for st in self.active_all():
            agms = _clean(st.get("agms"))
            if agms not in approved:
                continue
            try:
                sdt = datetime.fromisoformat(st["timestamp"])
            except Exception:
                continue
            threshold = start_at
            try:
                threshold = datetime.fromisoformat(_clean((initial.get(agms) or {}).get("timestamp")))
            except Exception:
                pass
            if threshold <= sdt < end_at:
                sessions.append({"start": st, "end": None, "start_dt": sdt, "end_dt": end_at if shift.get("end_at") else None})
        return sorted(sessions, key=lambda x: (_clean(x["start"].get("full_name")), x["start_dt"]))


    def list_shifts(self) -> list[dict]:
        result: list[dict] = []
        try:
            with self._shift_db_connect() as con:
                rows = con.execute("SELECT data_json FROM shifts ORDER BY start_at DESC").fetchall()
            for row in rows:
                try:
                    result.append(json.loads(row["data_json"]))
                except Exception:
                    continue
        except Exception:
            pass
        return result


    def search_finalized_shifts(
        self,
        date_from: date | None = None,
        date_to: date | None = None,
        officer_query: str = "",
        limit: int | None = None,
    ) -> list[dict]:
        clauses = ["status='FINALIZED'", "end_at IS NOT NULL", "end_at<>''"]
        params: list[object] = []
        if date_from is not None:
            clauses.append("start_at>=?")
            params.append(f"{date_from:%Y-%m-%d}T00:00:00")
        if date_to is not None:
            clauses.append("start_at<=?")
            params.append(f"{date_to:%Y-%m-%d}T23:59:59")

        sql = "SELECT data_json FROM shifts WHERE " + " AND ".join(clauses) + " ORDER BY start_at DESC"
        if limit is not None and int(limit) > 0:
            sql += " LIMIT ?"
            params.append(int(limit))

        result: list[dict] = []
        try:
            with self._shift_db_connect() as con:
                rows = con.execute(sql, params).fetchall()
            query = _clean(officer_query).upper()
            if query:
                query = "".join(ch for ch in unicodedata.normalize("NFD", query) if unicodedata.category(ch) != "Mn")
            for row in rows:
                try:
                    shift = json.loads(row["data_json"])
                except Exception:
                    continue
                if query:
                    officer = shift.get("start_officer") or shift.get("end_officer") or {}
                    haystack = _clean(
                        f"{officer.get('rank','')} {officer.get('surname','')} "
                        f"{officer.get('given_name','')} {officer.get('full_name','')} {officer.get('agms','')}"
                    ).upper()
                    haystack = "".join(ch for ch in unicodedata.normalize("NFD", haystack) if unicodedata.category(ch) != "Mn")
                    if query not in haystack:
                        continue
                result.append(shift)
        except Exception:
            return []
        return result


    def roster_sessions(self, start_at: datetime, agms_list: list[str] | tuple[str, ...], lookback_minutes: int = 30, horizon_hours: int = 12) -> list[dict]:
        allowed = {_clean(x) for x in agms_list if _clean(x)}
        search_start = start_at - timedelta(minutes=max(0, int(lookback_minutes)))
        search_end = start_at + timedelta(hours=max(1, int(horizon_hours)))
        events = self.iter_events(search_start, search_end)
        starts: dict[str, dict] = {_clean(e.get("event_id")): e for e in events if e.get("kind") == "START"}
        sessions: list[dict] = []
        for e in events:
            if _clean(e.get("agms")) not in allowed:
                continue
            if e.get("kind") == "START":
                starts[e.get("event_id", "")] = e
            elif e.get("kind") == "END":
                sid = e.get("start_event_id", "")
                st = starts.get(sid)
                if not st:
                    continue
                sdt = datetime.fromisoformat(st["timestamp"]); edt = datetime.fromisoformat(e["timestamp"])
                sessions.append({"start": st, "end": e, "start_dt": sdt, "end_dt": edt})
        for st in self.active_all():
            if _clean(st.get("agms")) not in allowed:
                continue
            try:
                sdt = datetime.fromisoformat(st["timestamp"])
            except Exception:
                continue
            if search_start <= sdt < search_end:
                sessions.append({"start": st, "end": None, "start_dt": sdt, "end_dt": None})
        return sorted(sessions, key=lambda x: (_clean(x["start"].get("full_name")), x["start_dt"]))


    def shift_sessions(self, day: date, cutoff: str = DEFAULT_CUTOFF) -> tuple[datetime, datetime, list[dict]]:
        hh, mm = [int(x) for x in cutoff.split(":", 1)]
        start_dt = datetime.combine(day, dtime(hh, mm))
        end_dt = start_dt + timedelta(days=1)
        # Read a wider window so sessions that started shortly before the cutoff can still be paired if needed.
        events = self.iter_events(start_dt - timedelta(days=1), end_dt)
        starts: dict[str, dict] = {_clean(e.get("event_id")): e for e in events if e.get("kind") == "START"}
        sessions: list[dict] = []
        for e in events:
            if e.get("kind") == "START":
                starts[e.get("event_id", "")] = e
            elif e.get("kind") == "END":
                sid = e.get("start_event_id", "")
                s = starts.get(sid)
                if not s:
                    continue
                sdt = datetime.fromisoformat(s["timestamp"])
                edt = datetime.fromisoformat(e["timestamp"])
                if edt <= start_dt or sdt >= end_dt:
                    continue
                sessions.append({"start": s, "end": e, "start_dt": sdt, "end_dt": edt})
        # Open sessions that fall in the selected shift.
        for s in self.active_all():
            try:
                sdt = datetime.fromisoformat(s["timestamp"])
            except Exception:
                continue
            if sdt < end_dt:
                sessions.append({"start": s, "end": None, "start_dt": sdt, "end_dt": None})
        sessions.sort(key=lambda x: (x["start"].get("full_name", ""), x["start_dt"]))
        return start_dt, end_dt, sessions


"""Pure shift report text/HTML formatting, independent of storage and Qt."""
from __future__ import annotations
from datetime import date, datetime
from typing import Protocol
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord


class ShiftSessionSource(Protocol):
    def shift_sessions(self, day: date, cutoff: str) -> tuple: ...
    def shift_sessions_v2(self, shift: dict) -> list[dict]: ...
    def roster_sessions(self, start_at: datetime, agms: list, lookback_minutes: int, max_window_hours: int) -> list[dict]: ...

GREEK_MONTH_GENITIVE = {
    1: "Ιανουαρίου", 2: "Φεβρουαρίου", 3: "Μαρτίου", 4: "Απριλίου",
    5: "Μαΐου", 6: "Ιουνίου", 7: "Ιουλίου", 8: "Αυγούστου",
    9: "Σεπτεμβρίου", 10: "Οκτωβρίου", 11: "Νοεμβρίου", 12: "Δεκεμβρίου",
}



def _duration_text(start_dt: datetime, end_dt: datetime | None) -> str:
    if end_dt is None:
        return "ΑΝΟΙΚΤΗ"
    minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"



def build_shift_text(store: ShiftSessionSource, day: date, cutoff: str) -> str:
    start_dt, end_dt, sessions = store.shift_sessions(day, cutoff)
    lines = [
        "ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ - ΑΝΑΦΟΡΑ ΒΑΡΔΙΑΣ",
        f"Από {start_dt:%d/%m/%Y %H:%M} έως {end_dt:%d/%m/%Y %H:%M}",
        "",
    ]
    by_person: dict[tuple[str, str], list[dict]] = {}
    for s in sessions:
        st = s["start"]
        key = (_clean(st.get("agms")), _clean(st.get("full_name")))
        by_person.setdefault(key, []).append(s)
    for (agms, name), items in sorted(by_person.items(), key=lambda x: x[0][1]):
        rank = _clean(items[0]["start"].get("rank"))
        lines.append(_clean(f"{rank} {name} (ΑΓΜΣ {agms})"))
        totals = {"ΕΙΣΟΔΟΣ": 0, "ΕΞΟΔΟΣ": 0}
        for item in items:
            st = item["start"]
            sdt = item["start_dt"]
            edt = item["end_dt"]
            end_text = edt.strftime("%H:%M:%S") if edt else "ΑΝΟΙΚΤΗ"
            lines.append(
                f"  Θ. {st.get('position','')} {st.get('direction','')} "
                f"{sdt:%H:%M:%S}–{end_text} ({_duration_text(sdt, edt)})"
            )
            if edt and st.get("direction") in totals:
                totals[st["direction"]] += max(0, int((edt - sdt).total_seconds()))
        for direction in ("ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"):
            sec = totals[direction]
            if sec:
                h, rem = divmod(sec, 3600)
                m = rem // 60
                lines.append(f"  Σύνολο {direction}: {h:02d}:{m:02d}")
        lines.append("")
    if not by_person:
        lines.append("Δεν υπάρχουν καταχωρίσεις για τη συγκεκριμένη βάρδια.")
    return "\n".join(lines)



def build_roster_shift_text(store: ShiftSessionSource, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> str:
    people_by_agms = people_by_agms or {}
    sessions = store.shift_sessions_v2(shift) if int(shift.get("version", 1)) >= 2 else store.roster_sessions(
        datetime.fromisoformat(shift["start_at"]), shift.get("agms", []), int(shift.get("lookback_minutes", 30)), int(shift.get("max_window_hours", 12))
    )
    if int(shift.get("version", 1)) < 2 and hasattr(store, "historical_session_items"):
        sessions += store.historical_session_items(shift["shift_id"])
    roster = [_clean(x) for x in (shift.get("approved", []) if int(shift.get("version", 1)) >= 2 else shift.get("agms", [])) if _clean(x)]
    for item in sessions:
        agms = _clean(item["start"].get("agms"))
        if item["start"].get("historical") and agms not in roster:
            roster.append(agms)

    by_agms: dict[str, list[dict]] = {a: [] for a in roster}
    for item in sessions:
        by_agms.setdefault(_clean(item["start"].get("agms")), []).append(item)
    start_at = datetime.fromisoformat(shift["start_at"])
    end_at = datetime.fromisoformat(shift.get("end_at")) if shift.get("end_at") else None
    lines = [
        "ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ",
        "Τ.Δ.Ε. ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ",
        "ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ ΒΑΡΔΙΑΣ",
        f"Βάρδια: {start_at:%d/%m/%Y %H:%M}" + (f" - {end_at:%d/%m/%Y %H:%M}" if end_at else " - ΣΕ ΕΞΕΛΙΞΗ"),
        "",
    ]
    for agms in roster:
        items = sorted(by_agms.get(agms, []), key=lambda x: x["start_dt"])
        person = people_by_agms.get(agms)
        if person:
            header = _clean(f"{person.rank} {person.surname} {person.given_name}")
        elif items:
            st = items[0]["start"]; header = _clean(f"{st.get('rank','')} {st.get('full_name','')}") or f"ΑΓΜΣ {agms}"
        else:
            header = f"ΑΓΜΣ {agms}"
        lines.append(header)
        if not items:
            lines.append("  Χωρίς καταχώριση θέσης")
        for item in items:
            st = item["start"]; sdt = item["start_dt"]; edt = item["end_dt"]
            end_text = edt.strftime("%H:%M") if edt else "ΑΝΟΙΚΤΗ"
            marker = " (ΙΣΤΟΡΙΚΗ ΚΑΤΑΧΩΡΙΣΗ)" if st.get("historical") else ""
            lines.append(f"  ΘΕΣΗ {st.get('position','')}   {sdt:%H:%M} - {end_text}{marker}")
        lines.append("")
    officer = shift.get("start_officer") or {}
    officer_name = _clean(f"{officer.get('rank','')} {officer.get('full_name','')}")
    lines.extend(["", "Ο ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ", officer_name, "Υπογραφή: __________________________"] )
    return "\n".join(lines)



def _format_seconds(total_seconds: int) -> str:
    total_minutes = max(0, int(total_seconds) // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"



def shift_report_title(shift: dict) -> str:
    start_at = datetime.fromisoformat(_clean(shift.get("start_at")))
    end_at = datetime.fromisoformat(_clean(shift.get("end_at")) or _clean(shift.get("start_at")))
    if start_at.year == end_at.year and start_at.month == end_at.month:
        period = f"{start_at.day:02d}-{end_at.day:02d} {GREEK_MONTH_GENITIVE[end_at.month]} {end_at.year}"
    elif start_at.year == end_at.year:
        period = (
            f"{start_at.day:02d} {GREEK_MONTH_GENITIVE[start_at.month]} - "
            f"{end_at.day:02d} {GREEK_MONTH_GENITIVE[end_at.month]} {end_at.year}"
        )
    else:
        period = (
            f"{start_at.day:02d} {GREEK_MONTH_GENITIVE[start_at.month]} {start_at.year} - "
            f"{end_at.day:02d} {GREEK_MONTH_GENITIVE[end_at.month]} {end_at.year}"
        )
    officer = shift.get("start_officer") or shift.get("end_officer") or {}
    officer_name = _clean(f"{officer.get('surname','')} {officer.get('given_name','')}") or _clean(officer.get("full_name")) or "ΧΩΡΙΣ ΟΝΟΜΑ"
    return f"Αναφορά {period} - {officer_name}"



def build_roster_shift_html(store: ShiftSessionSource, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> str:
    text = build_roster_shift_text(store, shift, people_by_agms)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Αναφορά Βάρδιας</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#183247}}pre{{font-family:Consolas,'Courier New',monospace;font-size:11pt;white-space:pre-wrap;line-height:1.45}}@media print{{body{{margin:12mm}}}}</style>
</head><body><pre>{_escape_html(text)}</pre></body></html>"""



def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")



def build_shift_html(store: ShiftSessionSource, day: date, cutoff: str) -> str:
    text = build_shift_text(store, day, cutoff)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Αναφορά Βάρδιας</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#183247}}pre{{font-family:Consolas,'Courier New',monospace;font-size:11pt;white-space:pre-wrap}}@media print{{body{{margin:12mm}}}}</style>
</head><body><pre>{_escape_html(text)}</pre></body></html>"""


"""A4 shift and personnel-history PDF reports; Qt loaded only when requested."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import tempfile
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord
from position_tracking_report_text import ShiftSessionSource as SharedEventStore, _escape_html, _format_seconds

def create_shift_pdf(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None, target: str | Path | None = None) -> Path:
    """Create the shift report directly as an A4 PDF, without Word."""
    try:
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
        from PySide6.QtPrintSupport import QPrinter
    except Exception as exc:
        raise RuntimeError("Δεν είναι διαθέσιμη η δημιουργία PDF.") from exc

    people_by_agms = people_by_agms or {}
    sessions = store.shift_sessions_v2(shift) if int(shift.get("version", 1)) >= 2 else store.roster_sessions(
        datetime.fromisoformat(shift["start_at"]),
        shift.get("agms", []),
        int(shift.get("lookback_minutes", 30)),
        int(shift.get("max_window_hours", 12)),
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
    if target is None:
        preview_dir = Path(tempfile.gettempdir()) / "TDE_Krystallopigis" / "pdf_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        target = preview_dir / "ΑΝΑΦΟΡΑ_ΒΑΡΔΙΑΣ.pdf"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    body_parts = [
        "<div class='head'>ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ</div>",
        "<div class='subhead'>Τ.Δ.Ε. ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ</div>",
        "<div class='subhead'>ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ ΒΑΡΔΙΑΣ</div>",
        "<div class='period'>" + _escape_html(
            f"{start_at:%d/%m/%Y %H:%M}" + (f" - {end_at:%d/%m/%Y %H:%M}" if end_at else " - ΣΕ ΕΞΕΛΙΞΗ")
        ) + "</div>",
    ]

    if not roster:
        body_parts.append("<p class='empty'>Δεν υπάρχουν καταχωρίσεις στη βάρδια.</p>")

    for agms in roster:
        items = sorted(by_agms.get(agms, []), key=lambda x: x["start_dt"])
        person = people_by_agms.get(agms)
        if person:
            name = _clean(f"{person.rank} {person.surname} {person.given_name}")
        elif items:
            st = items[0]["start"]
            name = _clean(f"{st.get('rank','')} {st.get('full_name','')}") or f"ΑΓΜΣ {agms}"
        else:
            name = f"ΑΓΜΣ {agms}"

        body_parts.append(f"<div class='person'>{_escape_html(name)}</div>")
        if not items:
            body_parts.append("<div class='row muted'>Χωρίς καταχώριση θέσης</div>")
        for item in items:
            st = item["start"]
            sdt = item["start_dt"]
            edt = item["end_dt"]
            end_text = edt.strftime("%H:%M") if edt else "ΑΝΟΙΚΤΗ"
            direction = _clean(st.get("direction")).upper()
            details = f"ΘΕΣΗ {st.get('position','')}"
            if direction:
                details += f"   {direction}"
            details += f"   {sdt:%H:%M} - {end_text}"
            if st.get("historical"):
                details += "   (ΙΣΤΟΡΙΚΗ ΚΑΤΑΧΩΡΙΣΗ)"
            body_parts.append(f"<div class='row'>{_escape_html(details)}</div>")

    officer = shift.get("start_officer") or shift.get("end_officer") or {}
    officer_name = _clean(f"{officer.get('rank','')} {officer.get('full_name','')}")
    place_date = f"Κρυσταλλοπηγή, την {end_at:%d/%m/%Y}" if end_at else "Κρυσταλλοπηγή, την __________"
    body_parts.extend([
        f"<div class='place'>{_escape_html(place_date)}</div>",
        "<div class='signature'><b>Ο ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ</b><br><br>"
        + _escape_html(officer_name)
        + "<br><br>Υπογραφή: __________________________</div>",
    ])

    html = """<!doctype html><html><head><meta charset='utf-8'><style>
        body { font-family: Arial, 'Segoe UI', sans-serif; font-size: 10.5pt; color: #000; }
        .head { text-align:center; font-size:14pt; font-weight:700; margin-bottom:4px; }
        .subhead { text-align:center; font-size:12.5pt; font-weight:700; margin-bottom:3px; }
        .period { text-align:center; margin:10px 0 18px 0; }
        .person { font-weight:700; margin-top:11px; margin-bottom:3px; }
        .row { margin-left:14px; margin-bottom:2px; }
        .muted { font-style:italic; }
        .empty { margin-top:20px; }
        .place { text-align:center; margin-top:28px; }
        .signature { text-align:center; margin-top:12px; }
    </style></head><body>""" + "".join(body_parts) + "</body></html>"

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(target))
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Millimeter)

    document = QTextDocument()
    document.setHtml(html)
    document.print_(printer)

    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("Δεν δημιουργήθηκε το PDF της αναφοράς.")
    return target



def summarize_personnel_history(rows: list[dict]) -> dict:
    total = 0
    by_direction: dict[str, int] = {}
    by_position: dict[str, int] = {}
    by_direction_position: dict[tuple[str, str], int] = {}
    people: set[str] = set()
    for row in rows:
        sec = max(0, int(row.get("duration_seconds") or 0))
        total += sec
        direction = _clean(row.get("direction")).upper() or "—"
        position = _clean(row.get("position")) or "—"
        agms = _clean(row.get("agms"))
        if agms:
            people.add(agms)
        by_direction[direction] = by_direction.get(direction, 0) + sec
        by_position[position] = by_position.get(position, 0) + sec
        key = (direction, position)
        by_direction_position[key] = by_direction_position.get(key, 0) + sec
    return {
        "total_seconds": total,
        "people": len(people),
        "by_direction": by_direction,
        "by_position": by_position,
        "by_direction_position": by_direction_position,
    }



def create_personnel_history_pdf(
    rows: list[dict],
    criteria: str,
    summary: dict | None = None,
    target: str | Path | None = None,
) -> Path:
    """Render the current personnel-history search as an on-demand PDF."""
    try:
        from PySide6.QtCore import QMarginsF
        from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
        from PySide6.QtPrintSupport import QPrinter
    except Exception as exc:
        raise RuntimeError("Δεν είναι διαθέσιμη η δημιουργία PDF.") from exc

    if not rows:
        raise ValueError("Δεν υπάρχουν αποτελέσματα για εξαγωγή σε PDF.")

    summary = summary or summarize_personnel_history(rows)
    if target is None:
        preview_dir = Path(tempfile.gettempdir()) / "TDE_Krystallopigis" / "pdf_preview"
        preview_dir.mkdir(parents=True, exist_ok=True)
        target = preview_dir / "ΙΣΤΟΡΙΚΟ_ΠΡΟΣΩΠΙΚΟΥ.pdf"
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    direction_lines = []
    for direction in ("ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"):
        seconds = int(summary.get("by_direction", {}).get(direction, 0))
        if not seconds:
            continue
        positions = []
        for (item_direction, position), sec in sorted(
            summary.get("by_direction_position", {}).items(),
            key=lambda x: (x[0][0], x[0][1]),
        ):
            if item_direction == direction and sec:
                positions.append(f"Θέση {position}: {_format_seconds(sec)}")
        detail = " · ".join(positions)
        direction_lines.append(
            f"<div><b>{_escape_html(direction)}:</b> {_format_seconds(seconds)}"
            + (f" &nbsp; ({_escape_html(detail)})" if detail else "")
            + "</div>"
        )

    body_rows = []
    for row in rows:
        try:
            sdt = datetime.fromisoformat(_clean(row.get("start_at")))
            edt = datetime.fromisoformat(_clean(row.get("end_at")))
            date_text = sdt.strftime("%d/%m/%Y")
            start_text = sdt.strftime("%H:%M:%S")
            end_text = edt.strftime("%H:%M:%S")
        except Exception:
            date_text = _clean(row.get("start_at"))[:10]
            start_text = _clean(row.get("start_at"))[11:19]
            end_text = _clean(row.get("end_at"))[11:19]
        name = _clean(f"{row.get('rank','')} {row.get('surname','')} {row.get('given_name','')}") or _clean(row.get("full_name"))
        cells = [
            date_text,
            _clean(row.get("agms")),
            name,
            _clean(row.get("position")),
            _clean(row.get("direction")),
            start_text,
            end_text,
            _format_seconds(int(row.get("duration_seconds") or 0)),
        ]
        body_rows.append("<tr>" + "".join(f"<td>{_escape_html(str(v))}</td>" for v in cells) + "</tr>")

    html = """<!doctype html><html><head><meta charset='utf-8'><style>
        body { font-family: Arial, 'Segoe UI', sans-serif; font-size: 9pt; color:#000; }
        h1 { text-align:center; font-size:14pt; margin:0 0 3px 0; }
        h2 { text-align:center; font-size:12pt; margin:0 0 12px 0; }
        .criteria { margin:8px 0 12px 0; padding:7px; border:1px solid #999; }
        .summary { margin:8px 0 12px 0; line-height:1.45; }
        table { width:100%; border-collapse:collapse; }
        th, td { border:1px solid #777; padding:4px; }
        th { font-weight:bold; background:#eee; }
        .right { text-align:right; }
    </style></head><body>
    <h1>ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ</h1>
    <h2>Τ.Δ.Ε. ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ — ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ</h2>
    <div class='criteria'><b>Κριτήρια:</b> """ + _escape_html(criteria or "Χωρίς πρόσθετα φίλτρα") + """</div>
    <div class='summary'>
      <div><b>Καταχωρίσεις:</b> """ + str(len(rows)) + """ &nbsp; <b>Άτομα:</b> """ + str(summary.get("people", 0)) + """</div>
      <div><b>Συνολικός χρόνος:</b> """ + _format_seconds(int(summary.get("total_seconds", 0))) + """</div>
      """ + "".join(direction_lines) + """
    </div>
    <table>
      <tr><th>ΗΜΕΡΟΜΗΝΙΑ</th><th>ΑΓΜΣ</th><th>ΟΝΟΜΑ</th><th>ΘΕΣΗ</th><th>ΚΑΤΕΥΘΥΝΣΗ</th><th>ΕΝΑΡΞΗ</th><th>ΛΗΞΗ</th><th>ΔΙΑΡΚΕΙΑ</th></tr>
      """ + "".join(body_rows) + """
    </table></body></html>"""

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(target))
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Landscape)
    printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Millimeter)
    document = QTextDocument()
    document.setHtml(html)
    document.print_(printer)
    if not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError("Δεν δημιουργήθηκε το PDF του ιστορικού προσωπικού.")
    return target



def archive_shift_pdf(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> Path:
    """Compatibility alias: reports are rendered on demand, not stored in the archive."""
    return create_shift_pdf(store, shift, people_by_agms)


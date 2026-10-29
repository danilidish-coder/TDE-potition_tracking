"""Personnel value records and read-only OOXML personnel/roster import.

No GUI, central store or application startup dependency. The legacy entry point
reexports these classes for existing callers and serialized class references.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from position_tracking_common import _clean

__all__ = ["PersonnelRecord", "PersonnelRepository", "ShiftRosterRepository"]


@dataclass(frozen=True)
class PersonnelRecord:
    agms: str
    rank: str
    surname: str
    given_name: str

    @property
    def full_name(self) -> str:
        return _clean(f"{self.surname} {self.given_name}")

    @property
    def display(self) -> str:
        return _clean(f"{self.agms} - {self.rank} {self.full_name}")


class PersonnelRepository:
    NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

    AGMS_ALIASES = {
        "ΑΓΜΣ", "AΓΜΣ", "AGMS", "ΑΓΜ", "AΓΜ", "ΑΡΙΘΜΟΣΜΗΤΡΩΟΥ",
        "ΑΡΙΘΜΗΤΡΩΟΥ", "ΜΗΤΡΩΟ", "ΑΡΜΗΤΡΩΟΥ", "ΑΡΙΘΜΟΣΜΗΤΡ",
    }
    RANK_ALIASES = {"ΒΑΘΜΟΣ", "ΒΑΘΜ", "ΒΑΘΜΙΔΑ", "RANK"}
    SURNAME_ALIASES = {"ΕΠΩΝΥΜΟ", "ΕΠΩΝ", "ΕΠΩΝΥΜΙΑ", "ΕΠΙΘΕΤΟ", "SURNAME", "LASTNAME"}
    GIVEN_ALIASES = {"ΟΝΟΜΑ", "FIRSTNAME", "GIVENNAME"}
    FULLNAME_ALIASES = {"ΟΝΟΜΑΤΕΠΩΝΥΜΟ", "ΟΝΟΜΑΕΠΩΝΥΜΟ", "FULLNAME"}

    @staticmethod
    def _col_index(ref: str) -> int:
        m = re.match(r"([A-Z]+)", ref.upper())
        if not m:
            return 0
        n = 0
        for ch in m.group(1):
            n = n * 26 + ord(ch) - 64
        return n - 1

    @staticmethod
    def _header_key(value: object) -> str:
        raw = _clean(value).upper()
        raw = "".join(ch for ch in unicodedata.normalize("NFD", raw) if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^0-9A-ZΑ-Ω]", "", raw)

    @staticmethod
    def _normalize_agms(value: object) -> str:
        s = _clean(value)
        if re.fullmatch(r"\d+\.0+", s):
            s = s.split(".", 1)[0]
        s = re.sub(r"\s+", "", s)
        return s

    @classmethod
    def _looks_like_agms(cls, value: object) -> bool:
        s = cls._normalize_agms(value)
        return bool(re.fullmatch(r"\d{4,12}", s))

    @classmethod
    def _read_sheets(cls, path: str | Path) -> list[list[dict[int, str]]]:
        p = BytesIO(path) if isinstance(path, bytes) else Path(path)
        if not isinstance(path, bytes) and not p.is_file():
            raise ValueError("Δεν βρέθηκε το αρχείο Excel.")
        if not isinstance(path, bytes) and p.suffix.lower() not in {".xlsx", ".xlsm"}:
            raise ValueError("Υποστηρίζονται αρχεία Excel .xlsx ή .xlsm.")
        try:
            with zipfile.ZipFile(p, "r") as z:
                shared: list[str] = []
                if "xl/sharedStrings.xml" in z.namelist():
                    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
                    for si in root.findall(f"{cls.NS}si"):
                        shared.append("".join((t.text or "") for t in si.iter(f"{cls.NS}t")))

                wb = ET.fromstring(z.read("xl/workbook.xml"))
                rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
                targets = {r.attrib.get("Id"): r.attrib.get("Target") for r in rels}
                sheets_el = wb.find(f"{cls.NS}sheets")
                if sheets_el is None or len(sheets_el) == 0:
                    raise ValueError("Το Excel δεν έχει φύλλο.")

                all_sheets: list[list[dict[int, str]]] = []
                for sheet in sheets_el:
                    rid = sheet.attrib.get(f"{cls.REL}id")
                    target = (targets.get(rid) or "worksheets/sheet1.xml").lstrip("/")
                    if not target.startswith("xl/"):
                        target = "xl/" + target
                    if target not in z.namelist():
                        continue
                    root = ET.fromstring(z.read(target))
                    rows: list[dict[int, str]] = []
                    for row in root.findall(f".//{cls.NS}row"):
                        cells: dict[int, str] = {}
                        for c in row.findall(f"{cls.NS}c"):
                            idx = cls._col_index(c.attrib.get("r", "A1"))
                            t = c.attrib.get("t")
                            if t == "inlineStr":
                                value = "".join((x.text or "") for x in c.iter(f"{cls.NS}t"))
                            else:
                                v = c.find(f"{cls.NS}v")
                                raw = "" if v is None else (v.text or "")
                                value = shared[int(raw)] if t == "s" and raw.isdigit() and int(raw) < len(shared) else raw
                            cells[idx] = _clean(value)
                        if cells:
                            rows.append(cells)
                    if rows:
                        all_sheets.append(rows)
                if not all_sheets:
                    raise ValueError("Το Excel είναι κενό.")
                return all_sheets
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise ValueError(f"Μη έγκυρο Excel: {exc}") from exc

    @classmethod
    def _header_col(cls, row: dict[int, str], aliases: set[str], fuzzy: str = "") -> int:
        for i, value in row.items():
            key = cls._header_key(value)
            if key in aliases:
                return i
            if fuzzy and fuzzy in key:
                return i
        return -1

    @classmethod
    def _find_personnel_layout(cls, rows: list[dict[int, str]]) -> tuple[int, dict[str, int]] | None:
        best = None
        best_score = -1
        for ridx, row in enumerate(rows[:12]):
            i_agms = cls._header_col(row, cls.AGMS_ALIASES)
            if i_agms < 0:
                for i, value in row.items():
                    key = cls._header_key(value)
                    if "ΑΓΜΣ" in key or "AGMS" in key or ("ΜΗΤΡΩ" in key and ("ΑΡΙΘ" in key or key == "ΜΗΤΡΩΟ")):
                        i_agms = i; break
            if i_agms < 0:
                continue
            i_full = cls._header_col(row, cls.FULLNAME_ALIASES, "ΟΝΟΜΑΤΕΠΩΝΥΜ")
            i_sur = cls._header_col(row, cls.SURNAME_ALIASES, "ΕΠΩΝ")
            i_given = cls._header_col(row, cls.GIVEN_ALIASES)
            if i_sur == i_full:
                i_sur = -1
            if i_given == i_full:
                i_given = -1
            layout = {
                "agms": i_agms,
                "rank": cls._header_col(row, cls.RANK_ALIASES, "ΒΑΘΜ"),
                "surname": i_sur,
                "given": i_given,
                "full": i_full,
            }
            score = 10 + sum(1 for k, v in layout.items() if k != "agms" and v >= 0)
            if score > best_score:
                best = (ridx, layout); best_score = score
        return best

    @classmethod
    def _infer_agms_col(cls, rows: list[dict[int, str]], known_agms: set[str] | None = None) -> int:
        known = {cls._normalize_agms(x) for x in (known_agms or set()) if cls._normalize_agms(x)}
        cols = sorted({c for row in rows[:100] for c in row})
        best_col, best_score = -1, -1.0
        for col in cols:
            vals = [cls._normalize_agms(row.get(col, "")) for row in rows[:100] if _clean(row.get(col, ""))]
            if not vals:
                continue
            matches = sum(1 for v in vals if v in known) if known else 0
            plausible = sum(1 for v in vals if cls._looks_like_agms(v))
            uniq = len(set(vals))
            score = matches * 1000 + plausible * 10 + uniq - max(0, len(vals) - plausible) * 2
            if plausible and score > best_score:
                best_col, best_score = col, score
        return best_col

    @classmethod
    def name_key(cls, value: object) -> str:
        """Accent-, case- and spacing-insensitive key for matching names."""
        return cls._header_key(value)

    @classmethod
    def find(cls, people, query: object) -> list[PersonnelRecord]:
        """Find people by AGMS (exact) or by surname / full name (any order).

        A name query matches when the typed text equals the surname, the full
        name in either order, or is the beginning of one of them (at least two
        letters). The caller decides what to do when several people match.
        """
        text = _clean(query)
        if not text:
            return []
        agms = cls._normalize_agms(text)
        exact = [p for p in people if p.agms == agms]
        if exact:
            return exact
        key = cls.name_key(text)
        if len(key) < 2 or key.isdigit():
            return []
        full = lambda p: cls.name_key(p.surname + p.given_name)
        full_rev = lambda p: cls.name_key(p.given_name + p.surname)
        same = [p for p in people if key in (cls.name_key(p.surname), full(p), full_rev(p))]
        if same:
            return same
        return [p for p in people if cls.name_key(p.surname).startswith(key)
                or full(p).startswith(key) or full_rev(p).startswith(key)]

    @classmethod
    def load(cls, path: str | Path) -> tuple[PersonnelRecord, ...]:
        sheets = cls._read_sheets(path)
        best_records: list[PersonnelRecord] = []
        for rows in sheets:
            layout_info = cls._find_personnel_layout(rows)
            if layout_info:
                header_row, layout = layout_info
                data_rows = rows[header_row + 1:]
            else:
                i_agms = cls._infer_agms_col(rows)
                if i_agms < 0:
                    continue
                header_row = -1
                layout = {"agms": i_agms, "rank": -1, "surname": -1, "given": -1, "full": -1}
                data_rows = rows
                # No titles at all: guess the name columns from the text columns
                # to the right of the AGMS (1 = full name, 2 = surname + name,
                # 3 or more = rank, surname, name).
                text_cols = [c for c in sorted({c for row in rows[:100] for c in row})
                             if c != i_agms and sum(1 for row in rows[:100] if re.search(r"[^\W\d_]", row.get(c, ""))) >=
                             max(1, sum(1 for row in rows[:100] if row.get(c, "")) // 2)]
                if len(text_cols) == 1:
                    layout["full"] = text_cols[0]
                elif len(text_cols) == 2:
                    layout["surname"], layout["given"] = text_cols
                elif len(text_cols) >= 3:
                    layout["rank"], layout["surname"], layout["given"] = text_cols[:3]

            merged: dict[str, PersonnelRecord] = {}
            order: list[str] = []
            for row in data_rows:
                def cell(i: int) -> str:
                    return _clean(row.get(i, "")) if i >= 0 else ""
                agms = cls._normalize_agms(cell(layout["agms"]))
                if not agms or not cls._looks_like_agms(agms):
                    continue
                rank = cell(layout["rank"])
                surname = cell(layout["surname"])
                given = cell(layout["given"])
                full = cell(layout["full"])
                if full and not surname and not given:
                    parts = full.split()
                    surname = parts[0] if parts else full
                    given = " ".join(parts[1:]) if len(parts) > 1 else ""
                rec = PersonnelRecord(agms, rank, surname, given)
                if agms not in merged:
                    merged[agms] = rec; order.append(agms)
                else:
                    old = merged[agms]
                    merged[agms] = PersonnelRecord(
                        agms,
                        old.rank or rec.rank,
                        old.surname or rec.surname,
                        old.given_name or rec.given_name,
                    )
            records = [merged[a] for a in order]
            if len(records) > len(best_records):
                best_records = records

        if not best_records:
            raise ValueError("Δεν εντοπίστηκε κανένας έγκυρος Α.Γ.Μ.Σ. στο Excel. Ελέγξτε μόνο ότι το αρχείο περιέχει αριθμούς μητρώου.")
        return tuple(best_records)


class ShiftRosterRepository:
    @classmethod
    def load_agms(cls, path: str | Path, known_agms: set[str] | list[str] | tuple[str, ...] | None = None) -> tuple[str, ...]:
        sheets = PersonnelRepository._read_sheets(path)
        known = {PersonnelRepository._normalize_agms(x) for x in (known_agms or []) if PersonnelRepository._normalize_agms(x)}
        best_values: list[str] = []
        best_score = -1

        for rows in sheets:
            agms_col = -1
            header_row = -1
            for ridx, row in enumerate(rows[:12]):
                col = PersonnelRepository._header_col(row, PersonnelRepository.AGMS_ALIASES)
                if col < 0:
                    for i, value in row.items():
                        key = PersonnelRepository._header_key(value)
                        if "ΑΓΜΣ" in key or "AGMS" in key or ("ΜΗΤΡΩ" in key and ("ΑΡΙΘ" in key or key == "ΜΗΤΡΩΟ")):
                            col = i; break
                if col >= 0:
                    agms_col = col; header_row = ridx; break

            if agms_col < 0 and known:
                cols = sorted({c for row in rows for c in row})
                matches_per_col = []
                for col in cols:
                    matches = sum(1 for row in rows if PersonnelRepository._normalize_agms(row.get(col, "")) in known)
                    matches_per_col.append((matches, col))
                matches_per_col.sort(reverse=True)
                if matches_per_col and matches_per_col[0][0] > 0:
                    agms_col = matches_per_col[0][1]

            if agms_col < 0:
                agms_col = PersonnelRepository._infer_agms_col(rows, known)
            if agms_col < 0:
                continue

            data_rows = rows[header_row + 1:] if header_row >= 0 else rows
            values: list[str] = []
            seen: set[str] = set()
            known_hits = 0
            for row in data_rows:
                value = PersonnelRepository._normalize_agms(row.get(agms_col, ""))
                if not value or not PersonnelRepository._looks_like_agms(value):
                    continue
                if value not in seen:
                    seen.add(value); values.append(value)
                    if value in known:
                        known_hits += 1
            score = len(values) + known_hits * 100
            if values and score > best_score:
                best_values = values; best_score = score

        if not best_values:
            raise ValueError("Δεν εντοπίστηκε κανένας έγκυρος Α.Γ.Μ.Σ. στο Excel βάρδιας. Το αρχείο μπορεί να έχει οποιεσδήποτε άλλες στήλες· χρειάζεται μόνο να περιέχει Α.Γ.Μ.Σ.")
        return tuple(best_values)


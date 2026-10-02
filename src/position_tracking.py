from __future__ import annotations

import json
import os
import hashlib
import shutil
import re
import subprocess
import socket
import sys
import tempfile
import time
import uuid
import zipfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta, time as dtime
from pathlib import Path
from xml.etree import ElementTree as ET

APP_NAME = "TDE Krystallopigis - Katagrafi Theseon"
SETTINGS_NAME = "position_tracking.settings.json"
DEFAULT_CUTOFF = "10:00"
STATISTICS_PIN_SHA256 = "ca444860f0e1ddca9596007253ea43b3a5133780b0a566d9a096a53568c063fb"


def _clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def _safe_name(value: str) -> str:
    v = re.sub(r"[^0-9A-Za-zΑ-Ωα-ω_-]+", "_", _clean(value))
    return v or "UNKNOWN"


def _app_dir() -> Path:
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()


def _exe_dir() -> Path:
    return _app_dir()


def _runtime_root() -> Path:
    root = _app_dir() / ".tde_runtime"
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            path = str(root)
            attrs = kernel32.GetFileAttributesW(path)
            invalid = 0xFFFFFFFF
            hidden = 0x00000002
            if attrs != invalid and not (attrs & hidden):
                kernel32.SetFileAttributesW(path, attrs | hidden)
        except Exception:
            pass
    return root


def _open_path(path: str | Path) -> None:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True) if p.suffix == "" else p.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(p)])


def _fallback_settings_path() -> Path:
    public = os.environ.get("PUBLIC")
    if public:
        return Path(public) / "Documents" / "TDE_Krystallopigis" / SETTINGS_NAME
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "TDE_Krystallopigis" / SETTINGS_NAME


def _settings_path() -> Path:
    try:
        return _runtime_root() / SETTINGS_NAME
    except Exception:
        return _fallback_settings_path()


@dataclass
class AppConfig:
    central_root: str = ""
    personnel_file: str = ""
    cutoff: str = DEFAULT_CUTOFF
    positions: list[str] | None = None
    admin_pin_hash: str = ""
    theme: str = "light"

    def __post_init__(self):
        booth_positions = [str(i) for i in range(1, 15)]
        if self.positions is None:
            self.positions = booth_positions
        else:
            cleaned = [_clean(x) for x in self.positions if _clean(x)]
            for pos in booth_positions:
                if pos not in cleaned:
                    cleaned.append(pos)
            self.positions = cleaned

    @classmethod
    def load(cls) -> "AppConfig":
        path = _settings_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                central_root=_clean(data.get("central_root")),
                personnel_file=_clean(data.get("personnel_file")),
                cutoff=_clean(data.get("cutoff")) or DEFAULT_CUTOFF,
                positions=[_clean(x) for x in data.get("positions", []) if _clean(x)] or None,
                admin_pin_hash=_clean(data.get("admin_pin_hash")),
                theme=(_clean(data.get("theme")).lower() if _clean(data.get("theme")).lower() in {"light", "dark"} else "light"),
            )
        except Exception:
            return cls()

    def save(self) -> Path:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return path


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
    RANK_ALIASES = {"ΒΑΘΜΟΣ", "ΒΑΘΜ", "RANK"}
    SURNAME_ALIASES = {"ΕΠΩΝΥΜΟ", "ΕΠΩΝ", "SURNAME", "LASTNAME"}
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
        p = Path(path)
        if not p.is_file():
            raise ValueError("Δεν βρέθηκε το αρχείο Excel.")
        if p.suffix.lower() not in {".xlsx", ".xlsm"}:
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


class BusyError(RuntimeError):
    pass


class SharedEventStore:
    def __init__(self, central_root: str | Path):
        root = Path(central_root)
        self.root = root if root.name == ".tde_runtime" else (root if root.name.upper() == "TDE_DATA" else root / "TDE_DATA")
        self.events = self.root / "events"
        self.active = self.root / "active"
        self.locks = self.root / "locks"
        self.reports = self.root / "reports"
        self.shifts = self.root / "shifts"
        self.audit = self.root / "audit"
        self.backups = self.root / "backups"
        self.current_docs = self.root / "current"
        self.archive = self.root / "archive"
        self.statistics = self.root / "statistics"
        for p in (self.events, self.active, self.locks, self.reports, self.shifts, self.audit, self.backups, self.current_docs, self.archive, self.statistics):
            p.mkdir(parents=True, exist_ok=True)

    def _active_path(self, agms: str) -> Path:
        return self.active / f"{_safe_name(agms)}.json"

    def _lock_path(self, agms: str) -> Path:
        return self.locks / f"{_safe_name(agms)}.lock"

    @contextmanager
    def officer_lock(self, agms: str, timeout: float = 6.0):
        path = self._lock_path(agms)
        deadline = time.monotonic() + timeout
        fd = None
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{socket.gethostname()}|{os.environ.get('USERNAME') or os.environ.get('USER') or ''}|{time.time()}".encode("utf-8", "ignore"))
                break
            except FileExistsError:
                try:
                    if time.time() - path.stat().st_mtime > 60:
                        path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise BusyError("Η καταχώριση χρησιμοποιείται αυτή τη στιγμή από άλλο σταθμό. Δοκιμάστε ξανά.")
                time.sleep(0.15)
        try:
            yield
        finally:
            try:
                if fd is not None:
                    os.close(fd)
            finally:
                path.unlink(missing_ok=True)

    @staticmethod
    def _atomic_json(path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)

    def get_active(self, agms: str) -> dict | None:
        path = self._active_path(agms)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception:
            return None

    def _write_event(self, event: dict) -> Path:
        dt = datetime.fromisoformat(event["timestamp"])
        folder = self.events / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%Y-%m-%d}"
        filename = f"{dt:%Y%m%d_%H%M%S_%f}_{event['event_id']}.json"
        path = folder / filename
        self._atomic_json(path, event)
        return path

    def start(self, person: PersonnelRecord, position: str, direction: str, when: datetime | None = None) -> dict:
        when = when or datetime.now()
        position = _clean(position)
        direction = _clean(direction).upper()
        if not position:
            raise ValueError("Επιλέξτε θέση.")
        if direction not in {"ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"}:
            raise ValueError("Επιλέξτε κατεύθυνση ΕΙΣΟΔΟΣ ή ΕΞΟΔΟΣ.")
        with self.officer_lock(person.agms):
            current = self.get_active(person.agms)
            if current:
                raise ValueError(
                    f"Υπάρχει ήδη ανοικτή θέση για {person.full_name}: "
                    f"{current.get('position','')} {current.get('direction','')} από {current.get('timestamp','')}. "
                    "Πρέπει πρώτα να γίνει ΛΗΞΗ."
                )
            event = {
                "version": 2,
                "event_id": uuid.uuid4().hex,
                "kind": "START",
                "timestamp": when.isoformat(timespec="seconds"),
                "agms": person.agms,
                "rank": person.rank,
                "surname": person.surname,
                "given_name": person.given_name,
                "full_name": person.full_name,
                "position": position,
                "direction": direction,
                "computer": socket.gethostname(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            }
            path = self._write_event(event)
            event["event_file"] = str(path)
            self._atomic_json(self._active_path(person.agms), event)
            try:
                self.sync_active_shift()
            except Exception:
                pass
            return event

    def end(self, person: PersonnelRecord, when: datetime | None = None) -> dict:
        when = when or datetime.now()
        with self.officer_lock(person.agms):
            current = self.get_active(person.agms)
            if not current:
                raise ValueError(f"Δεν υπάρχει ανοικτή θέση για {person.full_name}.")
            event = {
                "version": 2,
                "event_id": uuid.uuid4().hex,
                "kind": "END",
                "timestamp": when.isoformat(timespec="seconds"),
                "start_event_id": current.get("event_id", ""),
                "agms": person.agms,
                "rank": current.get("rank", person.rank),
                "surname": current.get("surname", person.surname),
                "given_name": current.get("given_name", person.given_name),
                "full_name": current.get("full_name", person.full_name),
                "position": current.get("position", ""),
                "direction": current.get("direction", ""),
                "computer": socket.gethostname(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            }
            self._write_event(event)
            self._active_path(person.agms).unlink(missing_ok=True)
            return event

    def active_all(self) -> list[dict]:
        result: list[dict] = []
        for path in sorted(self.active.glob("*.json")):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return sorted(result, key=lambda x: (_clean(x.get("direction")), _clean(x.get("position")), _clean(x.get("full_name"))))

    def iter_events(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        result: list[dict] = []
        current = start_dt.date()
        last = end_dt.date()
        while current <= last:
            folder = self.events / f"{current:%Y}" / f"{current:%m}" / f"{current:%Y-%m-%d}"
            if folder.exists():
                for path in sorted(folder.glob("*.json")):
                    try:
                        e = json.loads(path.read_text(encoding="utf-8"))
                        ts = datetime.fromisoformat(e.get("timestamp", ""))
                        if start_dt <= ts < end_dt:
                            result.append(e)
                    except Exception:
                        pass
            current += timedelta(days=1)
        return sorted(result, key=lambda e: e.get("timestamp", ""))

    def iter_all_events(self) -> list[dict]:
        result: list[dict] = []
        if not self.events.exists():
            return result
        for path in sorted(self.events.rglob("*.json")):
            try:
                event = json.loads(path.read_text(encoding="utf-8"))
                if _clean(event.get("timestamp")):
                    result.append(event)
            except Exception:
                pass
        return sorted(result, key=lambda e: _clean(e.get("timestamp")))

    def completed_sessions_all(self) -> list[dict]:
        starts: dict[str, dict] = {}
        sessions: list[dict] = []
        for event in self.iter_all_events():
            kind = _clean(event.get("kind")).upper()
            if kind == "START":
                starts[_clean(event.get("event_id"))] = event
            elif kind == "END":
                sid = _clean(event.get("start_event_id"))
                start = starts.get(sid)
                if not start:
                    continue
                try:
                    start_dt = datetime.fromisoformat(_clean(start.get("timestamp")))
                    end_dt = datetime.fromisoformat(_clean(event.get("timestamp")))
                except Exception:
                    continue
                if end_dt < start_dt:
                    continue
                sessions.append({"start": start, "end": event, "start_dt": start_dt, "end_dt": end_dt})
        return sessions

    def save_shift(self, start_at: datetime, agms_list: list[str] | tuple[str, ...], lookback_minutes: int = 30, source_file: str = "") -> dict:
        unique = []
        seen = set()
        for value in agms_list:
            agms = _clean(value)
            if agms and agms not in seen:
                seen.add(agms); unique.append(agms)
        if not unique:
            raise ValueError("Η βάρδια δεν έχει προσωπικό.")
        lookback = max(0, min(int(lookback_minutes), 180))
        shift_id = f"SHIFT_{start_at:%Y%m%d_%H%M%S}"
        existing_path = self.shifts / f"{shift_id}.json"
        if existing_path.exists():
            try:
                existing = json.loads(existing_path.read_text(encoding="utf-8"))
                if _clean(existing.get("status")).upper() == "FINALIZED":
                    raise ValueError("Η βάρδια έχει οριστικοποιηθεί και δεν μπορεί να αντικατασταθεί.")
            except ValueError:
                raise
            except Exception:
                pass
        data = {
            "version": 1,
            "shift_id": shift_id,
            "start_at": start_at.isoformat(timespec="seconds"),
            "lookback_minutes": lookback,
            "max_window_hours": 12,
            "source_file": _clean(source_file),
            "agms": unique,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "created_by": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "computer": socket.gethostname(),
            "status": "DRAFT",
        }
        self._atomic_json(self.shifts / f"{shift_id}.json", data)
        self.log_admin_action("SHIFT_SAVED", {"shift_id": shift_id, "people": len(unique), "lookback_minutes": lookback})
        return data

    def _current_shift_path(self) -> Path:
        return self.shifts / "CURRENT_SHIFT.json"

    def current_shift(self) -> dict | None:
        path = self._current_shift_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if _clean(data.get("status")).upper() == "ACTIVE" else None
        except Exception:
            return None

    @staticmethod
    def _person_payload(person: PersonnelRecord) -> dict:
        return {
            "agms": person.agms, "rank": person.rank, "surname": person.surname,
            "given_name": person.given_name, "full_name": person.full_name,
        }

    def start_officer_shift(
        self,
        officer: PersonnelRecord,
        when: datetime | None = None,
        initial_approved: list[str] | tuple[str, ...] | None = None,
        initial_excluded: list[str] | tuple[str, ...] | None = None,
    ) -> dict:
        if self.current_shift():
            raise ValueError("Υπάρχει ήδη ενεργή βάρδια. Πρέπει πρώτα να γίνει ΛΗΞΗ ΒΑΡΔΙΑΣ.")
        when = when or datetime.now()
        active_now = self.active_all()
        active_by_agms = {}
        for item in active_now:
            agms = _clean(item.get("agms"))
            if agms and agms not in active_by_agms:
                active_by_agms[agms] = item

        if initial_approved is None and initial_excluded is None:
            approved = list(active_by_agms)
            excluded = []
        else:
            approved = []
            seen = set()
            for value in initial_approved or []:
                agms = _clean(value)
                if agms and agms in active_by_agms and agms not in seen:
                    approved.append(agms); seen.add(agms)
            excluded = []
            for value in initial_excluded or []:
                agms = _clean(value)
                if agms and agms in active_by_agms and agms not in seen:
                    excluded.append(agms); seen.add(agms)
            for agms in active_by_agms:
                if agms not in seen:
                    excluded.append(agms)

        # Κρατάμε την πραγματική ώρα έναρξης ΟΛΩΝ όσων είναι ήδη ενεργοί
        # κατά την έναρξη της βάρδιας, ακόμη κι αν αρχικά εξαιρεθούν.
        # Έτσι μια μεταγενέστερη διόρθωση ΕΞΑΙΡΕΣΗ -> ΑΠΟΔΟΧΗ
        # επαναφέρει πλήρως την πραγματική αρχική ώρα εργασίας.
        initial_active = {}
        for agms, item in active_by_agms.items():
            initial_active[agms] = {
                "timestamp": _clean(item.get("timestamp")),
                "event_id": _clean(item.get("event_id")),
            }

        shift = {
            "version": 2,
            "shift_id": f"SHIFT_{when:%Y%m%d_%H%M%S_%f}",
            "status": "ACTIVE",
            "start_at": when.isoformat(timespec="seconds"),
            "start_officer": self._person_payload(officer),
            "approved": approved,
            "excluded": excluded,
            "pending": [],
            "initial_active": initial_active,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._atomic_json(self._current_shift_path(), shift)
        self.log_admin_action("SHIFT_STARTED", {
            "shift_id": shift["shift_id"],
            "officer_agms": officer.agms,
            "initial_people": len(approved),
            "initial_excluded": len(excluded),
        })
        return shift

    def sync_active_shift(self) -> dict | None:
        shift = self.current_shift()
        if not shift:
            return None
        approved = [_clean(x) for x in shift.get("approved", []) if _clean(x)]
        excluded = [_clean(x) for x in shift.get("excluded", []) if _clean(x)]
        pending = [_clean(x) for x in shift.get("pending", []) if _clean(x)]
        known = set(approved) | set(excluded) | set(pending)
        changed = False
        for item in self.active_all():
            agms = _clean(item.get("agms"))
            if agms and agms not in known:
                pending.append(agms); known.add(agms); changed = True
        if changed:
            shift["pending"] = pending
            shift["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._atomic_json(self._current_shift_path(), shift)
        return shift

    def set_shift_member_state(self, agms: str, state: str) -> dict:
        shift = self.current_shift()
        if not shift:
            raise ValueError("Δεν υπάρχει ενεργή βάρδια.")
        agms = _clean(agms)
        state = _clean(state).upper()
        if state not in {"APPROVED", "EXCLUDED"}:
            raise ValueError("Μη έγκυρη κατάσταση μέλους βάρδιας.")
        for key in ("approved", "excluded", "pending"):
            shift[key] = [x for x in shift.get(key, []) if _clean(x) != agms]
        shift["approved" if state == "APPROVED" else "excluded"].append(agms)
        shift["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self._atomic_json(self._current_shift_path(), shift)
        self.log_admin_action("SHIFT_MEMBER_STATE", {"shift_id": shift["shift_id"], "agms": agms, "state": state})
        return shift

    def end_officer_shift(self, officer: PersonnelRecord, when: datetime | None = None) -> dict:
        shift = self.sync_active_shift()
        if not shift:
            raise ValueError("Δεν υπάρχει ενεργή βάρδια.")
        if shift.get("pending"):
            raise ValueError("Υπάρχουν άτομα σε ΑΝΑΜΟΝΗ. Κάντε πρώτα ΑΠΟΔΟΧΗ ή ΕΞΑΙΡΕΣΗ.")
        when = when or datetime.now()
        shift["status"] = "FINALIZED"
        shift["end_at"] = when.isoformat(timespec="seconds")
        shift["end_officer"] = self._person_payload(officer)
        shift["finalized_at"] = datetime.now().isoformat(timespec="seconds")
        final_path = self.shifts / f"{shift['shift_id']}.json"
        self._atomic_json(final_path, shift)
        self._current_shift_path().unlink(missing_ok=True)
        self.log_admin_action("SHIFT_ENDED", {"shift_id": shift["shift_id"], "officer_agms": officer.agms, "approved": len(shift.get("approved", [])), "excluded": len(shift.get("excluded", []))})
        return shift

    def shift_sessions_v2(self, shift: dict) -> list[dict]:
        approved = {_clean(x) for x in shift.get("approved", []) if _clean(x)}
        if not approved:
            return []
        start_at = datetime.fromisoformat(shift["start_at"])
        end_at = datetime.fromisoformat(shift.get("end_at") or datetime.now().isoformat(timespec="seconds"))
        initial = shift.get("initial_active", {}) or {}
        search_start = start_at
        for agms in approved:
            try:
                ts = datetime.fromisoformat(_clean((initial.get(agms) or {}).get("timestamp")))
                if ts < search_start:
                    search_start = ts
            except Exception:
                pass
        events = self.iter_events(search_start, end_at + timedelta(seconds=1))
        starts: dict[str, dict] = {}
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
        result = []
        for path in sorted(self.shifts.glob("SHIFT_*.json"), reverse=True):
            try:
                result.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                pass
        return result

    def roster_sessions(self, start_at: datetime, agms_list: list[str] | tuple[str, ...], lookback_minutes: int = 30, horizon_hours: int = 12) -> list[dict]:
        allowed = {_clean(x) for x in agms_list if _clean(x)}
        search_start = start_at - timedelta(minutes=max(0, int(lookback_minutes)))
        search_end = start_at + timedelta(hours=max(1, int(horizon_hours)))
        events = self.iter_events(search_start, search_end)
        starts: dict[str, dict] = {}
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

    def log_admin_action(self, action: str, details: dict | None = None) -> Path:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": _clean(action),
            "details": details or {},
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "computer": socket.gethostname(),
        }
        path = self.audit / "admin_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def backup_data(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = self.backups / f"TDE_DATA_BACKUP_{stamp}.zip"
        temp = target.with_suffix(target.suffix + ".tmp")
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in self.root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.root)
                except Exception:
                    continue
                if rel.parts and rel.parts[0].lower() == "backups":
                    continue
                zf.write(path, arcname=str(rel))
        os.replace(temp, target)
        self.log_admin_action("BACKUP_CREATED", {"file": str(target)})
        return target

    def finalize_shift(self, shift: dict, report_text: str = "") -> dict:
        shift_id = _clean(shift.get("shift_id"))
        if not shift_id:
            raise ValueError("Μη έγκυρη βάρδια.")
        path = self.shifts / f"{shift_id}.json"
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("Δεν βρέθηκε η βάρδια για οριστικοποίηση.") from exc
        if _clean(current.get("status")).upper() == "FINALIZED":
            return current
        current["status"] = "FINALIZED"
        current["finalized_at"] = datetime.now().isoformat(timespec="seconds")
        current["finalized_by"] = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        current["finalized_computer"] = socket.gethostname()
        if report_text:
            report_path = self.reports / f"FINAL_{shift_id}.txt"
            report_path.write_text(report_text, encoding="utf-8")
            current["final_report"] = str(report_path)
            current["final_report_sha256"] = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        self._atomic_json(path, current)
        self.log_admin_action("SHIFT_FINALIZED", {"shift_id": shift_id, "people": len(current.get("agms", []))})
        return current

    def shift_sessions(self, day: date, cutoff: str = DEFAULT_CUTOFF) -> tuple[datetime, datetime, list[dict]]:
        hh, mm = [int(x) for x in cutoff.split(":", 1)]
        start_dt = datetime.combine(day, dtime(hh, mm))
        end_dt = start_dt + timedelta(days=1)
        # Read a wider window so sessions that started shortly before the cutoff can still be paired if needed.
        events = self.iter_events(start_dt - timedelta(days=1), end_dt)
        starts: dict[str, dict] = {}
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


def _duration_text(start_dt: datetime, end_dt: datetime | None) -> str:
    if end_dt is None:
        return "ΑΝΟΙΚΤΗ"
    minutes = max(0, int((end_dt - start_dt).total_seconds() // 60))
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def build_shift_text(store: SharedEventStore, day: date, cutoff: str) -> str:
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


def build_roster_shift_text(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> str:
    people_by_agms = people_by_agms or {}
    sessions = store.shift_sessions_v2(shift) if int(shift.get("version", 1)) >= 2 else store.roster_sessions(
        datetime.fromisoformat(shift["start_at"]), shift.get("agms", []), int(shift.get("lookback_minutes", 30)), int(shift.get("max_window_hours", 12))
    )
    roster = [_clean(x) for x in (shift.get("approved", []) if int(shift.get("version", 1)) >= 2 else shift.get("agms", [])) if _clean(x)]
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
            lines.append(f"  ΘΕΣΗ {st.get('position','')}   {sdt:%H:%M} - {end_text}")
        lines.append("")
    officer = shift.get("start_officer") or {}
    officer_name = _clean(f"{officer.get('rank','')} {officer.get('full_name','')}")
    lines.extend(["", "Ο ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ", officer_name, "Υπογραφή: __________________________"] )
    return "\n".join(lines)


def create_personnel_statistics_xlsx(store: SharedEventStore, people_by_agms: dict[str, PersonnelRecord], target: str | Path | None = None) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.chart import PieChart, Reference
        from openpyxl.chart.label import DataLabelList
        from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
    except Exception as exc:
        raise RuntimeError("Δεν είναι διαθέσιμη η δημιουργία Excel στατιστικών (openpyxl).") from exc

    target_path = Path(target) if target else (store.statistics / "ΣΤΑΤΙΣΤΙΚΑ_ΠΡΟΣΩΠΙΚΟΥ.xlsx")
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Συγκέντρωση μόνο ολοκληρωμένων START/END συνεδριών.
    stats: dict[str, dict[tuple[str, str], int]] = {}
    for session in store.completed_sessions_all():
        start = session["start"]
        agms = _clean(start.get("agms"))
        if not agms:
            continue
        pos = _clean(start.get("position")) or "—"
        direction = _clean(start.get("direction")).upper() or "—"
        minutes = max(0, int((session["end_dt"] - session["start_dt"]).total_seconds() // 60))
        stats.setdefault(agms, {})[(pos, direction)] = stats.setdefault(agms, {}).get((pos, direction), 0) + minutes

    wb = Workbook()
    ws = wb.active
    ws.title = "ΣΤΑΤΙΣΤΙΚΑ"
    ws.sheet_view.showGridLines = False

    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "ΣΤΑΤΙΣΤΙΚΑ ΘΕΣΕΩΝ ΠΡΟΣΩΠΙΚΟΥ"
    c.font = Font(bold=True, color="FFFFFF", size=13)
    c.fill = PatternFill("solid", fgColor="1F4E78")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 24

    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 15
    ws.column_dimensions["C"].width = 19
    ws.column_dimensions["D"].width = 3
    for col in ("E", "F", "G", "H"):
        ws.column_dimensions[col].width = 12

    thin = Side(style="thin", color="D0D0D0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    name_fill = PatternFill("solid", fgColor="D9EAF7")
    header_fill = PatternFill("solid", fgColor="EDF4FA")

    people = sorted(people_by_agms.values(), key=lambda p: (p.surname, p.given_name, p.agms))
    row = 4
    for person in people:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        name_cell = ws.cell(row=row, column=1, value=_clean(f"{person.rank} {person.full_name}"))
        name_cell.font = Font(bold=True, size=11)
        name_cell.fill = name_fill
        name_cell.alignment = Alignment(vertical="center")

        hdr = row + 1
        headers = ["ΘΕΣΗ", "ΚΑΤΕΥΘΥΝΣΗ", "ΣΥΝΟΛΙΚΟΣ ΧΡΟΝΟΣ"]
        for col_idx, text in enumerate(headers, 1):
            cell = ws.cell(row=hdr, column=col_idx, value=text)
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = border

        entries = sorted((stats.get(person.agms) or {}).items(), key=lambda x: (x[0][0], x[0][1]))
        if not entries:
            entries = [(('—', '—'), 0)]

        data_start = hdr + 1
        pie_by_position: dict[str, int] = {}
        for (pos, direction), minutes in entries:
            ws.cell(row=row+2, column=1, value=pos).font = Font(bold=True)
            ws.cell(row=row+2, column=2, value=direction)
            duration_cell = ws.cell(row=row+2, column=3, value=(minutes / 1440 if minutes else 0))
            duration_cell.number_format = '[h]" ώ "mm" λ"'
            for col_idx in range(1, 4):
                cell = ws.cell(row=row+2, column=col_idx)
                cell.alignment = Alignment(horizontal="center")
                cell.border = border
            pie_by_position[pos] = pie_by_position.get(pos, 0) + minutes
            row += 1

        data_end = row + 1
        # Κρυφά βοηθητικά δεδομένα μόνο για την πίτα.
        helper_start = hdr
        ws.cell(row=helper_start, column=11, value="ΘΕΣΗ")
        ws.cell(row=helper_start, column=12, value="ΛΕΠΤΑ")
        helper_row = helper_start + 1
        for pos, minutes in sorted(pie_by_position.items()):
            ws.cell(row=helper_row, column=11, value=pos)
            ws.cell(row=helper_row, column=12, value=minutes)
            helper_row += 1
        ws.column_dimensions["K"].hidden = True
        ws.column_dimensions["L"].hidden = True

        if any(v > 0 for v in pie_by_position.values()):
            chart = PieChart()
            labels = Reference(ws, min_col=11, min_row=helper_start+1, max_row=helper_row-1)
            data = Reference(ws, min_col=12, min_row=helper_start, max_row=helper_row-1)
            chart.add_data(data, titles_from_data=True)
            chart.set_categories(labels)
            chart.title = ""
            chart.height = 4.3
            chart.width = 7.0
            chart.legend.position = "b"
            chart.dataLabels = DataLabelList()
            chart.dataLabels.showPercent = True
            ws.add_chart(chart, f"E{hdr-1}")

        row = max(row + 4, hdr + 8)

    temp = target_path.with_suffix(target_path.suffix + ".tmp")
    wb.save(temp)
    os.replace(temp, target_path)
    return target_path


def create_shift_docx(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None, target: str | Path | None = None) -> Path:
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except Exception as exc:
        raise RuntimeError("Δεν είναι διαθέσιμη η δημιουργία Word (python-docx).") from exc
    people_by_agms = people_by_agms or {}
    sessions = store.shift_sessions_v2(shift) if int(shift.get("version", 1)) >= 2 else []
    roster = [_clean(x) for x in shift.get("approved", []) if _clean(x)]
    by_agms: dict[str, list[dict]] = {a: [] for a in roster}
    for item in sessions:
        by_agms.setdefault(_clean(item["start"].get("agms")), []).append(item)
    start_at = datetime.fromisoformat(shift["start_at"])
    end_at = datetime.fromisoformat(shift.get("end_at")) if shift.get("end_at") else None
    if target is None:
        target = store.current_docs / "ΤΡΕΧΟΥΣΑ_ΒΑΡΔΙΑ.docx"
    target = Path(target); target.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    normal = doc.styles["Normal"]; normal.font.name = "Arial"; normal.font.size = Pt(11)
    for text, size, bold in [("ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ", 14, True), ("Τ.Δ.Ε. ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ", 13, True), ("ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ ΒΑΡΔΙΑΣ", 13, True)]:
        p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(text); r.bold = bold; r.font.size = Pt(size)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"{start_at:%d/%m/%Y %H:%M}" + (f" - {end_at:%d/%m/%Y %H:%M}" if end_at else " - ΣΕ ΕΞΕΛΙΞΗ"))
    doc.add_paragraph()
    for agms in roster:
        items = sorted(by_agms.get(agms, []), key=lambda x: x["start_dt"])
        person = people_by_agms.get(agms)
        if person:
            name = _clean(f"{person.rank} {person.surname} {person.given_name}")
        elif items:
            st = items[0]["start"]; name = _clean(f"{st.get('rank','')} {st.get('full_name','')}") or f"ΑΓΜΣ {agms}"
        else:
            name = f"ΑΓΜΣ {agms}"
        p = doc.add_paragraph(); p.add_run(name).bold = True
        if not items:
            doc.add_paragraph("Χωρίς καταχώριση θέσης", style=None)
        for item in items:
            st = item["start"]; sdt = item["start_dt"]; edt = item["end_dt"]
            end_text = edt.strftime("%H:%M") if edt else "ΑΝΟΙΚΤΗ"
            p = doc.add_paragraph()
            r = p.add_run(f"ΘΕΣΗ {st.get('position','')}")
            r.bold = True
            direction = _clean(st.get("direction")).upper()
            if direction:
                p.add_run(f"   {direction}")
            p.add_run(f"   {sdt:%H:%M} - {end_text}")
    doc.add_paragraph()
    officer = shift.get("start_officer") or {}
    officer_name = _clean(f"{officer.get('rank','')} {officer.get('full_name','')}")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run(f"Κρυσταλλοπηγή, την {end_at:%d/%m/%Y}" if end_at else "Κρυσταλλοπηγή, την __________")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.add_run("Ο ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ").bold = True
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.add_run(officer_name).bold = True
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER; p.add_run("Υπογραφή: __________________________")
    doc.save(target)
    return target


GREEK_MONTH_GENITIVE = {
    1: "Ιανουαρίου", 2: "Φεβρουαρίου", 3: "Μαρτίου", 4: "Απριλίου",
    5: "Μαΐου", 6: "Ιουνίου", 7: "Ιουλίου", 8: "Αυγούστου",
    9: "Σεπτεμβρίου", 10: "Οκτωβρίου", 11: "Νοεμβρίου", 12: "Δεκεμβρίου",
}


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


def archive_shift_docx(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> Path:
    stamp = datetime.fromisoformat(_clean(shift.get("end_at")) or _clean(shift.get("start_at")))
    folder = store.archive / f"{stamp:%Y}" / f"{stamp:%m}" / f"{stamp:%Y-%m-%d}"
    folder.mkdir(parents=True, exist_ok=True)
    filename = re.sub(r'[<>:"/\\|?*]+', "_", shift_report_title(shift)).strip() + ".docx"
    target = folder / filename
    return create_shift_docx(store, shift, people_by_agms, target)


def build_roster_shift_html(store: SharedEventStore, shift: dict, people_by_agms: dict[str, PersonnelRecord] | None = None) -> str:
    text = build_roster_shift_text(store, shift, people_by_agms)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Αναφορά Βάρδιας</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#183247}}pre{{font-family:Consolas,'Courier New',monospace;font-size:11pt;white-space:pre-wrap;line-height:1.45}}@media print{{body{{margin:12mm}}}}</style>
</head><body><pre>{_escape_html(text)}</pre></body></html>"""


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_shift_html(store: SharedEventStore, day: date, cutoff: str) -> str:
    text = build_shift_text(store, day, cutoff)
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>Αναφορά Βάρδιας</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:28px;color:#183247}}pre{{font-family:Consolas,'Courier New',monospace;font-size:11pt;white-space:pre-wrap}}@media print{{body{{margin:12mm}}}}</style>
</head><body><pre>{_escape_html(text)}</pre></body></html>"""


def run(args=None) -> int:
    from PySide6.QtCore import Qt, QDate, QDateTime, QTimer, QRectF
    from PySide6.QtGui import QColor, QFont, QPainter, QPen, QIcon, QPixmap, QPalette
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDateEdit, QFormLayout, QFrame, QHBoxLayout,
        QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
        QInputDialog, QDialog, QDateTimeEdit, QSpinBox, QListWidget, QListWidgetItem, QFileDialog, QToolButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
    )

    THEME_DARK = {
        "window": "#07111f", "panel": "#0d1b2b", "card": "#10243a", "card2": "#132c46",
        "text": "#f4f8ff", "muted": "#93a8bf", "accent": "#1378d4", "accent2": "#0b5ea8",
        "border": "#214565", "danger": "#b73a4a", "ok": "#1f9d70", "input": "#0a1726",
    }
    THEME_LIGHT = {
        "window": "#eaf1f8", "panel": "#f6f9fc", "card": "#ffffff", "card2": "#eef5fb",
        "text": "#0d2238", "muted": "#587086", "accent": "#0c68bd", "accent2": "#084d8c",
        "border": "#c4d5e5", "danger": "#b12f41", "ok": "#16795a", "input": "#ffffff",
    }

    def _theme_stylesheet(theme: str) -> str:
        t = THEME_DARK if _clean(theme).lower() == "dark" else THEME_LIGHT
        return f"""
            QMainWindow, QWidget#rootPanel {{ background: {t['window']}; color: {t['text']}; }}
            QWidget {{ color: {t['text']}; font-family:'Segoe UI'; font-size:10.5pt; }}
            QDialog {{ background: {t['window']}; color: {t['text']}; }}
            QDialog QLabel {{ color: {t['text']}; }}

            QFrame#card {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['card2']},stop:0.10 {t['card']},stop:1 {t['card']});
                border:1px solid {t['border']}; border-radius:16px;
            }}
            QLabel#statusBox, QLabel#infoBox {{
                background:{t['card2']}; border:1px solid {t['border']}; border-radius:10px;
                padding:9px; color:{t['muted']}; font-weight:700;
            }}

            QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QSpinBox {{
                background:{t['input']}; color:{t['text']}; border:2px solid {t['border']};
                border-radius:10px; min-height:36px; padding:4px 9px;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QSpinBox:focus {{
                border:2px solid {t['accent']}; background:{t['card']};
            }}
            QComboBox {{ padding-right:28px; }}
            QComboBox::drop-down {{
                width:28px; border-left:1px solid {t['border']}; background:{t['card2']};
                border-top-right-radius:8px; border-bottom-right-radius:8px;
            }}
            QComboBox QAbstractItemView {{
                background:{t['card2']}; color:{t['text']}; border:2px solid {t['accent']};
                selection-background-color:{t['accent']}; selection-color:white; outline:0; padding:4px;
            }}
            QListWidget, QTableWidget, QTextBrowser {{
                background:{t['input']}; color:{t['text']}; border:2px solid {t['border']};
                border-radius:9px; alternate-background-color:{t['card2']};
                selection-background-color:{t['accent']}; selection-color:white;
            }}
            QListWidget::item {{ padding:6px; }}
            QListWidget::item:selected {{ background:{t['accent']}; color:white; }}
            QHeaderView::section {{
                background:{t['card2']}; color:{t['text']}; border:1px solid {t['border']};
                padding:6px; font-weight:700;
            }}

            QPushButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['card2']},stop:1 {t['panel']});
                color:{t['text']}; border:1px solid {t['border']}; border-bottom:3px solid {t['window']};
                border-radius:12px; padding:7px 14px; font-weight:750;
            }}
            QPushButton:hover {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});
                color:white; border-color:{t['accent']}; border-bottom-color:{t['window']};
            }}
            QPushButton:pressed {{
                background:{t['accent2']}; border-bottom-width:1px; padding-top:9px;
            }}
            QPushButton:disabled {{
                color:{t['muted']}; background:{t['panel']}; border-color:{t['border']};
            }}
            QToolButton {{
                background:{t['card2']}; color:{t['text']}; border:1px solid {t['border']};
                border-radius:12px; padding:8px 12px; font-weight:700;
            }}
            QToolButton:hover {{
                background:{t['accent']}; color:white; border-color:{t['accent']};
            }}
            QPushButton#startButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['ok']},stop:1 #0d5f46);
                color:white; border-color:{t['ok']}; border-bottom:3px solid {t['window']};
                font-size:17px; font-weight:900; text-align:center;
            }}
            QPushButton#endButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['danger']},stop:1 #6f1f2d);
                color:white; border-color:{t['danger']}; border-bottom:3px solid {t['window']};
                font-size:17px; font-weight:900; text-align:center;
            }}
        """

    def _network_icon() -> QIcon:
        pixmap = QPixmap(256, 256)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#0a4f8c"))
        painter.drawRoundedRect(18, 18, 220, 220, 48, 48)
        nodes = [(128, 128, 28), (66, 72, 22), (190, 72, 22), (66, 184, 22), (190, 184, 22)]
        painter.setPen(QPen(QColor("#8fd0ff"), 12, Qt.SolidLine, Qt.RoundCap))
        for x, y, _ in nodes[1:]:
            painter.drawLine(128, 128, x, y)
        for x, y, radius in nodes:
            painter.setPen(QPen(QColor("#dff3ff"), 5))
            painter.setBrush(QColor("#1976c9") if (x, y) != (128, 128) else QColor("#f5f9ff"))
            painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
        painter.end()
        return QIcon(pixmap)

    class BoothMapWidget(QWidget):
        BOOTH_POS = {
            "7": (0.46, 0.10), "6": (0.52, 0.10),
            "5": (0.52, 0.24), "4": (0.52, 0.32),
            "3": (0.40, 0.40), "2": (0.46, 0.40), "1": (0.52, 0.40),
            "10": (0.40, 0.64), "9": (0.46, 0.64), "8": (0.52, 0.64),
            "11": (0.52, 0.72), "12": (0.52, 0.80),
            "14": (0.46, 0.90), "13": (0.52, 0.90),
        }

        def __init__(self, parent=None):
            super().__init__(parent)
            self.active: dict[str, list[dict]] = {}
            self.setMinimumSize(760, 560)

        def set_active(self, items: list[dict]):
            grouped: dict[str, list[dict]] = {}
            for item in items:
                grouped.setdefault(_clean(item.get("position")), []).append(item)
            self.active = grouped
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            painter.fillRect(self.rect(), QColor("#06101c"))

            # ground / lanes
            painter.setPen(QPen(QColor("#17364e"), 1))
            step = 42
            for x in range(0, w, step): painter.drawLine(x, 0, x, h)
            for y in range(0, h, step): painter.drawLine(0, y, w, y)
            painter.setPen(QPen(QColor("#69849a"), 2, Qt.DashLine))
            for frac in (0.18, 0.34, 0.68, 0.84):
                y = int(h * frac); painter.drawLine(30, y, w - 30, y)

            # buildings
            painter.setPen(QPen(QColor("#38bdf8"), 2))
            painter.setBrush(QColor("#162638"))
            buildings = [(0.10,0.49,0.22,0.10,"ΤΕΛΩΝΕΙΟ"),(0.34,0.49,0.22,0.10,"ΑΣΤΥΝΟΜΙΑ"),(0.58,0.49,0.15,0.10,"ΑΞ/ΚΟΣ ΥΠΗΡΕΣΙΑΣ")]
            painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
            for x,y,bw,bh,label in buildings:
                r=QRectF(w*x,h*y,w*bw,h*bh); painter.drawRoundedRect(r,8,8); painter.drawText(r,Qt.AlignCenter,label)

            # labels
            painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
            painter.setPen(QColor("#4ade80")); painter.drawText(QRectF(w*0.76,h*0.18,w*0.20,h*0.08),Qt.AlignCenter,"ΕΙΣΟΔΟΣ ↑")
            painter.setPen(QColor("#f87171")); painter.drawText(QRectF(w*0.76,h*0.70,w*0.20,h*0.08),Qt.AlignCenter,"ΕΞΟΔΟΣ ↓")

            # booths
            bw = max(54, int(w*0.075)); bh = max(46, int(h*0.075))
            for pos,(xf,yf) in self.BOOTH_POS.items():
                x=int(w*xf); y=int(h*yf)
                r=QRectF(x,y,bw,bh)
                people=self.active.get(pos,[])
                occupied=bool(people)
                # subtle pseudo-3D depth: shadow + lower/right faces, then main face
                shadow_r = QRectF(r.x()+7, r.y()+8, r.width(), r.height())
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, 95))
                painter.drawRoundedRect(shadow_r, 9, 9)
                painter.setBrush(QColor("#0f5f3f" if occupied else "#064865"))
                painter.drawRoundedRect(QRectF(r.x()+4, r.y()+5, r.width(), r.height()), 9, 9)
                painter.setPen(QPen(QColor("#a7f3d0" if occupied else "#bae6fd"),2))
                painter.setBrush(QColor("#1f9d68" if occupied else "#0878a8"))
                painter.drawRoundedRect(r,9,9)
                # highlight on upper edge for a raised/card-like effect
                painter.setPen(QPen(QColor(255,255,255,70),1))
                painter.drawLine(int(r.x()+7), int(r.y()+4), int(r.right()-7), int(r.y()+4))
                painter.setPen(QColor("#ffffff"))
                painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
                painter.drawText(QRectF(r.x(),r.y()+2,r.width(),18),Qt.AlignCenter,f"ΘΕΣΗ {pos}")
                if people:
                    names=[]
                    for item in people[:2]:
                        surname=_clean(item.get("surname")) or _clean(item.get("full_name"))
                        ts=_clean(item.get("timestamp")).replace("T"," ")
                        hhmm=ts[11:16] if len(ts)>=16 else ""
                        direction=_clean(item.get("direction"))
                        names.append(f"{surname}\n{direction} {hhmm}".strip())
                    if len(people)>2: names.append(f"+{len(people)-2} ακόμη")
                    painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                    painter.drawText(QRectF(r.x()+3,r.y()+19,r.width()-6,r.height()-21),Qt.AlignCenter|Qt.TextWordWrap,"\n".join(names))

    class LiveMapDialog(QDialog):
        def __init__(self, store: SharedEventStore, parent=None):
            super().__init__(parent)
            self.store = store
            self.setWindowTitle("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ - Ζωντανή εικόνα θέσεων")
            self.resize(1100, 760)
            self.setStyleSheet("""
                QDialog{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #eef5f9,stop:1 #dfeaf1);}
                QLabel{color:#193b50;}
            """)
            lay=QVBoxLayout(self); lay.setContentsMargins(22,22,22,22); lay.setSpacing(14)
            top=QHBoxLayout()
            title=QLabel("ΖΩΝΤΑΝΗ ΕΙΚΟΝΑ ΘΕΣΕΩΝ"); title.setStyleSheet("font-size:22px;font-weight:900;color:#123f5a;letter-spacing:1px")
            self.updated=QLabel("")
            top.addWidget(title); top.addStretch(); top.addWidget(self.updated)
            lay.addLayout(top)
            self.map=BoothMapWidget(); lay.addWidget(self.map,1)
            self.other=QLabel(""); self.other.setWordWrap(True); self.other.setStyleSheet("background:#ffffff;border:1px solid #cfdae2;padding:10px 12px;border-radius:12px;color:#36596f;font-weight:600")
            lay.addWidget(self.other)
            self.timer=QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(2000)
            self.refresh()

        def refresh(self):
            items=self.store.active_all()
            self.map.set_active(items)
            other=[]
            for x in items:
                pos=_clean(x.get("position"))
                if pos not in BoothMapWidget.BOOTH_POS:
                    other.append(f"{x.get('rank','')} {x.get('full_name','')} — {pos} — {x.get('direction','')} — από {_clean(x.get('timestamp')).replace('T',' ')}")
            self.other.setText("Άλλες ενεργές θέσεις: " + (" | ".join(other) if other else "καμία"))
            self.updated.setText("Ενημέρωση: " + datetime.now().strftime("%H:%M:%S"))

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.config = AppConfig.load()
            self.people: tuple[PersonnelRecord, ...] = ()
            self._people_by_agms: dict[str, PersonnelRecord] = {}
            self.store: SharedEventStore | None = None
            self._pending_prompt_active = False
            self._last_shift_signature = ""
            self.setWindowTitle("Τ.Δ.Ε. Κρυσταλλοπηγής - Καταγραφή Θέσεων")
            self.resize(1120, 690)
            self.setMinimumSize(980, 620)
            self._build()
            self._apply_config()
            self._apply_theme()
            self.shift_timer = QTimer(self)
            self.shift_timer.timeout.connect(self._check_shift_updates)
            self.shift_timer.start(3000)

        def _build(self):
            self.root = QWidget(); self.root.setObjectName("rootPanel"); self.setCentralWidget(self.root)
            outer = QVBoxLayout(self.root); outer.setContentsMargins(28,22,28,20); outer.setSpacing(14)

            header = QHBoxLayout()
            titles = QVBoxLayout(); titles.setSpacing(2)
            self.title_label = QLabel("Τ.Δ.Ε. ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ")
            self.title_label.setStyleSheet("font-size:25px;font-weight:900;letter-spacing:1px")
            self.subtitle_label = QLabel("ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ")
            self.subtitle_label.setStyleSheet("font-size:15px;font-weight:800;letter-spacing:2px")
            titles.addWidget(self.title_label); titles.addWidget(self.subtitle_label)
            header.addLayout(titles); header.addStretch()

            self.theme_btn = QToolButton()
            self.theme_btn.setMinimumWidth(112)
            self.theme_btn.setMinimumHeight(34)
            self.theme_btn.clicked.connect(self._toggle_theme)
            header.addWidget(self.theme_btn)
            outer.addLayout(header)

            columns = QHBoxLayout(); columns.setSpacing(16)

            self.operator_card = QFrame(); self.operator_card.setObjectName("card")
            left = QVBoxLayout(self.operator_card); left.setContentsMargins(20,18,20,18); left.setSpacing(12)
            self.operator_title = QLabel("ΠΡΟΣΩΠΙΚΟ")
            self.operator_title.setAlignment(Qt.AlignCenter); self.operator_title.setStyleSheet("font-size:18px;font-weight:900")
            left.addWidget(self.operator_title)
            operator_form = QFormLayout(); operator_form.setSpacing(12)

            self.agms_input = QLineEdit(); self.agms_input.setPlaceholderText("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.agms_input.setMinimumHeight(42); self.agms_input.textChanged.connect(self._agms_changed)
            self.person_name = QLabel("—"); self.person_name.setWordWrap(True); self.person_name.setStyleSheet("font-size:16px;font-weight:800")
            self.direction = QComboBox(); self.direction.addItems(["ΕΙΣΟΔΟΣ","ΕΞΟΔΟΣ"]); self.direction.setMinimumHeight(42)
            self.position = QComboBox(); self.position.setMinimumHeight(42); self.position.currentTextChanged.connect(self._position_changed)
            operator_form.addRow("Α.Γ.Μ.Σ.", self.agms_input)
            operator_form.addRow("Αστυνομικός", self.person_name)
            operator_form.addRow("ΚΑΤΕΥΘΥΝΣΗ", self.direction)
            operator_form.addRow("ΘΕΣΗ", self.position)
            left.addLayout(operator_form)

            self.active_status = QLabel("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.active_status.setObjectName("statusBox")
            self.active_status.setAlignment(Qt.AlignCenter); self.active_status.setWordWrap(True)
            left.addWidget(self.active_status)
            left.addStretch()

            op_buttons = QHBoxLayout(); op_buttons.setSpacing(12)
            self.start_btn = QPushButton("ΕΝΑΡΞΗ"); self.start_btn.setObjectName("startButton"); self.start_btn.setMinimumHeight(54)
            self.end_btn = QPushButton("ΛΗΞΗ"); self.end_btn.setObjectName("endButton"); self.end_btn.setMinimumHeight(54)
            self.start_btn.clicked.connect(self._start); self.end_btn.clicked.connect(self._end)
            op_buttons.addWidget(self.start_btn); op_buttons.addWidget(self.end_btn)
            left.addLayout(op_buttons)

            self.officer_card = QFrame(); self.officer_card.setObjectName("card")
            right = QVBoxLayout(self.officer_card); right.setContentsMargins(22,18,22,18); right.setSpacing(13)
            self.officer_title = QLabel("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ")
            self.officer_title.setAlignment(Qt.AlignCenter); self.officer_title.setStyleSheet("font-size:18px;font-weight:900")
            right.addWidget(self.officer_title)

            officer_form = QFormLayout(); officer_form.setSpacing(12)
            self.officer_agms = QLineEdit(); self.officer_agms.setPlaceholderText("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.officer_agms.setMinimumHeight(42); self.officer_agms.textChanged.connect(self._officer_changed)
            self.officer_name = QLabel("—"); self.officer_name.setWordWrap(True); self.officer_name.setStyleSheet("font-size:16px;font-weight:800")
            officer_form.addRow("Α.Γ.Μ.Σ.", self.officer_agms)
            officer_form.addRow("Αξιωματικός", self.officer_name)
            right.addLayout(officer_form)

            self.shift_status = QLabel("Δεν υπάρχει ενεργή βάρδια.")
            self.shift_status.setAlignment(Qt.AlignCenter); self.shift_status.setWordWrap(True); self.shift_status.setObjectName("statusBox")
            right.addWidget(self.shift_status)
            right.addStretch()

            shift_buttons = QHBoxLayout(); shift_buttons.setSpacing(12)
            self.start_shift_btn = QPushButton("ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ"); self.start_shift_btn.setObjectName("startButton"); self.start_shift_btn.setMinimumHeight(54)
            self.end_shift_btn = QPushButton("ΛΗΞΗ ΒΑΡΔΙΑΣ"); self.end_shift_btn.setObjectName("endButton"); self.end_shift_btn.setMinimumHeight(54)
            self.start_shift_btn.clicked.connect(self._start_officer_shift_ui)
            self.end_shift_btn.clicked.connect(self._end_officer_shift_ui)
            shift_buttons.addWidget(self.start_shift_btn); shift_buttons.addWidget(self.end_shift_btn)
            right.addLayout(shift_buttons)

            columns.addWidget(self.operator_card, 1); columns.addWidget(self.officer_card, 1)
            outer.addLayout(columns, 1)

            bottom = QHBoxLayout(); bottom.setSpacing(10)
            self.print_btn = QPushButton("ΤΡΕΧΟΥΣΑ ΑΝΑΦΟΡΑ")
            self.archive_btn = QPushButton("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ")
            self.history_btn = QPushButton("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
            for b in (self.print_btn, self.archive_btn, self.history_btn):
                b.setMinimumHeight(44)
                bottom.addWidget(b)
            self.print_btn.clicked.connect(self._report)
            self.archive_btn.clicked.connect(self._report_archive)
            self.history_btn.clicked.connect(self._personnel_history)
            outer.addLayout(bottom)

            bottom2 = QHBoxLayout(); bottom2.setSpacing(10)
            self.active_positions_btn = QPushButton("ΕΝΕΡΓΕΣ ΘΕΣΕΙΣ ΕΡΓΑΣΙΑΣ")
            self.personnel_list_btn = QPushButton("ΕΠΙΛΟΓΗ ΛΙΣΤΑΣ ΠΡΟΣΩΠΙΚΟΥ")
            for b in (self.active_positions_btn, self.personnel_list_btn):
                b.setMinimumHeight(44)
                bottom2.addWidget(b)
            self.active_positions_btn.clicked.connect(self._live_map)
            self.personnel_list_btn.clicked.connect(self._choose_personnel_list)
            outer.addLayout(bottom2)

            self.info = QLabel(""); self.info.setObjectName("infoBox"); self.info.setAlignment(Qt.AlignCenter); self.info.setWordWrap(True)
            outer.addWidget(self.info)
            self.credits = QLabel("ΑΝΘ/ΜΟΣ ΔΑΝΙΗΛΙΔΗΣ ΗΡΑΚΛΗΣ   •   ΑΝΘ/ΜΟΣ ΚΛΙΑΝΗΣ ΧΡΗΣΤΟΣ")
            self.credits.setAlignment(Qt.AlignCenter)
            outer.addWidget(self.credits)

        def _toggle_theme(self):
            self.config.theme = "light" if _clean(self.config.theme).lower() == "dark" else "dark"
            self.config.save()
            self._apply_theme()

        def _apply_theme(self):
            dark = _clean(self.config.theme).lower() == "dark"
            t = THEME_DARK if dark else THEME_LIGHT

            self.setUpdatesEnabled(False)
            self.root.setUpdatesEnabled(False)
            try:
                palette = self.palette()
                palette.setColor(QPalette.Window, QColor(t["window"]))
                self.setPalette(palette)
                self.setAutoFillBackground(True)

                root_palette = self.root.palette()
                root_palette.setColor(QPalette.Window, QColor(t["window"]))
                self.root.setPalette(root_palette)
                self.root.setAutoFillBackground(True)

                self.setStyleSheet(_theme_stylesheet(self.config.theme))
                self.theme_btn.setText("☀ ΦΩΤΕΙΝΟ" if dark else "☾ ΣΚΟΤΕΙΝΟ")
                self.subtitle_label.setStyleSheet(
                    f"font-size:15px;font-weight:800;letter-spacing:2px;color:{t['muted']}"
                )
                self.credits.setStyleSheet(f"color:{t['muted']};font-size:9px")
                self._agms_changed()
                self._officer_changed()
            finally:
                self.root.setUpdatesEnabled(True)
                self.setUpdatesEnabled(True)
                self.update()

        def _find_personnel_file(self) -> Path | None:
            candidates = []
            legacy = Path(self.config.personnel_file) if _clean(self.config.personnel_file) else None
            if legacy and legacy.is_file():
                candidates.append(legacy)
            for base in (_runtime_root(), _app_dir() / "CONFIG", _app_dir()):
                for name in ("ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"):
                    candidates.append(base / name)
            for path in candidates:
                if path.is_file():
                    return path
            return None

        def _apply_config(self):
            self.position.clear(); self.position.addItems(self.config.positions or [])
            self._position_changed(self.position.currentText())
            try:
                self.store = SharedEventStore(_runtime_root())
                self.config.central_root = str(_runtime_root())
            except Exception as exc:
                self.store = None
                self.info.setText(f"Πρόβλημα .tde_runtime: {exc}")
            personnel = self._find_personnel_file()
            if personnel:
                try:
                    self._load_people(str(personnel)); self.config.personnel_file = str(personnel)
                except Exception as exc:
                    self.info.setText(f"Πρόβλημα προσωπικού: {exc}")
            self.config.save()
            self._refresh_info(); self._agms_changed(); self._refresh_shift_status()

        def _refresh_info(self):
            if self.store and self.people:
                self.info.setText(f"Σύστημα έτοιμο — Λίστα προσωπικού: {len(self.people)} άτομα")
            elif not self.store:
                self.info.setText("Δεν είναι διαθέσιμος ο φάκελος δεδομένων.")
            else:
                self.info.setText("Δεν έχει επιλεγεί λίστα προσωπικού.")

        def _save_config(self):
            self.config.positions = [self.position.itemText(i) for i in range(self.position.count()) if _clean(self.position.itemText(i))]
            self.config.save(); self._refresh_info()

        def _load_people(self, path: str):
            self.people = PersonnelRepository.load(path)
            self._people_by_agms = {_clean(p.agms): p for p in self.people}
            self._agms_changed(); self._officer_changed()

        def _choose_personnel_list(self):
            start_dir = str(Path(self.config.personnel_file).parent) if _clean(self.config.personnel_file) else str(_app_dir())
            path, _ = QFileDialog.getOpenFileName(self, "Επιλογή λίστας προσωπικού", start_dir, "Excel (*.xlsx *.xlsm)")
            if not path:
                return
            try:
                self._load_people(path)
                self.config.personnel_file = path
                self.config.save()
                if self.store:
                    self.store.log_admin_action("PERSONNEL_LIST_SELECTED", {"file": path, "people": len(self.people)})
                self._refresh_info()
                QMessageBox.information(self, "Λίστα προσωπικού", f"Επιλέχθηκε λίστα με {len(self.people)} άτομα.\nΘα χρησιμοποιείται αυτόματα στις επόμενες εκκινήσεις.")
            except Exception as exc:
                QMessageBox.critical(self, "Λίστα προσωπικού", f"Δεν ήταν δυνατή η ανάγνωση του αρχείου.\n{exc}")

        def _selected(self) -> PersonnelRecord | None:
            return self._people_by_agms.get(_clean(self.agms_input.text()))

        def _officer_selected(self) -> PersonnelRecord | None:
            return self._people_by_agms.get(_clean(self.officer_agms.text()))

        def _officer_changed(self, *_):
            p = self._officer_selected()
            self.officer_name.setText(_clean(f"{p.rank} {p.surname} {p.given_name}") if p else "—")
            self._refresh_shift_status()

        def _agms_changed(self, *_):
            p = self._selected()
            if not p:
                self.person_name.setText("—")
                self.active_status.setText("Ο Α.Γ.Μ.Σ. δεν βρέθηκε στο προσωπικό" if _clean(self.agms_input.text()) else "Πληκτρολογήστε Α.Γ.Μ.Σ.")
                self.start_btn.setEnabled(False); self.end_btn.setEnabled(False)
                return
            self.person_name.setText(_clean(f"{p.rank} {p.surname} {p.given_name}"))
            active = self.store.get_active(p.agms) if self.store else None
            if active:
                ts = _clean(active.get("timestamp","")).replace("T"," ")
                self.active_status.setText(f"ΕΝΕΡΓΗ: ΘΕΣΗ {active.get('position','')} — {active.get('direction','')} — από {ts}")
                self.start_btn.setEnabled(False); self.end_btn.setEnabled(True)
            else:
                self.active_status.setText("Δεν υπάρχει ανοικτή καταχώριση")
                self.start_btn.setEnabled(bool(self.store)); self.end_btn.setEnabled(False)

        @staticmethod
        def _suggested_direction(position: str) -> str:
            pos = _clean(position)
            if pos.isdigit():
                n = int(pos)
                if 1 <= n <= 7: return "ΕΙΣΟΔΟΣ"
                if 8 <= n <= 14: return "ΕΞΟΔΟΣ"
            return "ΕΙΣΟΔΟΣ"

        def _position_changed(self, position: str):
            suggested = self._suggested_direction(position)
            idx = self.direction.findText(suggested)
            if idx >= 0: self.direction.setCurrentIndex(idx)

        def _start(self):
            p = self._selected()
            if not p or not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού."); return
            pos = _clean(self.position.currentText())
            direction = _clean(self.direction.currentText()).upper()
            try:
                if pos not in {str(i) for i in range(1,15)}: raise ValueError("Επιλέξτε θέση 1 έως 14.")
                e = self.store.start(p,pos,direction)
                QMessageBox.information(self,"Καταχώριση",f"ΕΝΑΡΞΗ: ΘΕΣΗ {pos} — {direction}\nΏρα: {e['timestamp'].replace('T',' ')}")
                self._agms_changed()
                QTimer.singleShot(150, self._check_shift_updates)
            except Exception as exc:
                QMessageBox.critical(self,"Δεν καταχωρίστηκε",str(exc))

        def _end(self):
            p = self._selected()
            if not p or not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού."); return
            try:
                e=self.store.end(p)
                QMessageBox.information(self,"Καταχώριση",f"ΛΗΞΗ καταχωρίστηκε στις {e['timestamp'].replace('T',' ')}")
                self._agms_changed()
            except Exception as exc:
                QMessageBox.critical(self,"Δεν καταχωρίστηκε",str(exc))

        def _preview_list_dialog(self, title: str, intro: str, agms_list: list[str], allow_exclude: bool) -> tuple[bool,list[str],list[str]]:
            dlg=QDialog(self); dlg.setWindowTitle(title); dlg.resize(620,480)
            lay=QVBoxLayout(dlg); lay.setContentsMargins(20,18,20,18); lay.setSpacing(10)
            heading=QLabel(title); heading.setStyleSheet("font-size:18px;font-weight:900")
            text_label=QLabel(intro); text_label.setWordWrap(True)
            lay.addWidget(heading); lay.addWidget(text_label)
            listing=QListWidget()
            for agms in agms_list:
                p=self._people_by_agms.get(_clean(agms))
                name=_clean(f"{p.rank} {p.surname} {p.given_name}") if p else f"ΑΓΜΣ {agms}"
                item=QListWidgetItem(f"{agms} — {name}")
                item.setData(Qt.UserRole,_clean(agms))
                if allow_exclude:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                listing.addItem(item)
            lay.addWidget(listing,1)
            buttons=QHBoxLayout(); cancel=QPushButton("ΑΚΥΡΩΣΗ"); confirm=QPushButton("ΕΠΙΒΕΒΑΙΩΣΗ")
            cancel.clicked.connect(dlg.reject); confirm.clicked.connect(dlg.accept)
            buttons.addStretch(); buttons.addWidget(cancel); buttons.addWidget(confirm); lay.addLayout(buttons)
            if dlg.exec()!=QDialog.Accepted:
                return False,[],[]
            approved=[]; excluded=[]
            for i in range(listing.count()):
                item=listing.item(i); agms=_clean(item.data(Qt.UserRole))
                if allow_exclude and item.checkState()!=Qt.Checked: excluded.append(agms)
                else: approved.append(agms)
            return True,approved,excluded

        def _start_officer_shift_ui(self):
            if not self.store:
                QMessageBox.warning(self,"Έλεγχος","Δεν είναι διαθέσιμος ο φάκελος δεδομένων."); return
            p=self._officer_selected()
            if not p:
                QMessageBox.warning(self,"Έλεγχος","Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
            if self.store.current_shift():
                QMessageBox.warning(self,"Βάρδια","Υπάρχει ήδη ενεργή βάρδια."); return
            active=self.store.active_all()
            agms=[]
            for item in active:
                a=_clean(item.get("agms"))
                if a and a not in agms: agms.append(a)
            ok,approved,excluded=self._preview_list_dialog(
                "ΠΡΟΕΠΙΣΚΟΠΗΣΗ ΕΝΑΡΞΗΣ ΒΑΡΔΙΑΣ",
                "Ελέγξτε το προσωπικό που βρίσκεται ήδη σε ενεργή θέση. Αποεπιλέξτε όποιον δεν πρέπει να συμπεριληφθεί στη νέα βάρδια.",
                agms, True
            )
            if not ok: return
            try:
                shift=self.store.start_officer_shift(p,initial_approved=approved,initial_excluded=excluded)
                self._last_shift_signature=""
                self._refresh_shift_status()
                QMessageBox.information(self,"Βάρδια",f"Η βάρδια ξεκίνησε στις {shift['start_at'].replace('T',' ')}.")
            except Exception as exc:
                QMessageBox.critical(self,"Βάρδια",str(exc))

        def _resolve_pending_members(self) -> bool:
            if not self.store or self._pending_prompt_active:
                return False
            shift=self.store.sync_active_shift()
            pending=list(shift.get("pending",[])) if shift else []
            if not pending:
                return True
            self._pending_prompt_active=True
            try:
                for agms in pending:
                    p=self._people_by_agms.get(_clean(agms))
                    name=_clean(f"{p.rank} {p.surname} {p.given_name}") if p else f"ΑΓΜΣ {agms}"
                    answer=QMessageBox.question(
                        self,
                        "Νέο άτομο στη βάρδια",
                        f"{name}\n\nΚαταγράφηκε σε θέση μετά την έναρξη της βάρδιας.\nΝα συμπεριληφθεί στη βάρδια;",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if answer == QMessageBox.Yes:
                        self.store.set_shift_member_state(agms, "APPROVED")
                    else:
                        confirm_exclusion = QMessageBox.question(
                            self,
                            "Επιβεβαίωση εξαίρεσης",
                            f"{name}\n\nΕίστε βέβαιοι ότι θέλετε να ΕΞΑΙΡΕΣΕΤΕ το άτομο από τη βάρδια;",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if confirm_exclusion == QMessageBox.Yes:
                            self.store.set_shift_member_state(agms, "EXCLUDED")
            finally:
                self._pending_prompt_active=False
            self._refresh_shift_status()
            return True

        def _end_officer_shift_ui(self):
            if not self.store:
                return
            p=self._officer_selected()
            if not p:
                QMessageBox.warning(self,"Έλεγχος","Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
            shift=self.store.sync_active_shift()
            if not shift:
                QMessageBox.information(self,"Βάρδια","Δεν υπάρχει ενεργή βάρδια."); return
            if shift.get("pending"):
                self._resolve_pending_members()
                shift=self.store.sync_active_shift()
                if shift and shift.get("pending"):
                    return
            approved=list(shift.get("approved",[]))
            ok,_,_=self._preview_list_dialog(
                "ΕΠΙΒΕΒΑΙΩΣΗ ΛΗΞΗΣ ΒΑΡΔΙΑΣ",
                "Αυτά είναι τα άτομα που θα συμπεριληφθούν στην τελική βάρδια. Επιβεβαιώστε για να ολοκληρωθεί η λήξη.",
                approved, False
            )
            if not ok: return
            try:
                final=self.store.end_officer_shift(p)
                archive=archive_shift_docx(self.store,final,self._people_by_agms)
                create_shift_docx(self.store,final,self._people_by_agms)
                self._refresh_shift_status()
                QMessageBox.information(self,"Λήξη βάρδιας",f"Η βάρδια ολοκληρώθηκε.\nΑρχειοθετήθηκε: {archive}")
            except Exception as exc:
                QMessageBox.critical(self,"Λήξη βάρδιας",str(exc))

        def _refresh_shift_status(self):
            if not hasattr(self,"shift_status"): return
            shift=self.store.current_shift() if self.store else None
            p=self._officer_selected() if hasattr(self,"officer_agms") else None
            if not shift:
                self.shift_status.setText("Δεν υπάρχει ενεργή βάρδια.")
                self.start_shift_btn.setEnabled(bool(p and self.store))
                self.end_shift_btn.setEnabled(False)
                return
            st=datetime.fromisoformat(shift["start_at"])
            off=shift.get("start_officer") or {}
            name=_clean(f"{off.get('rank','')} {off.get('full_name','')}")
            pending=len(shift.get("pending",[]))
            text=f"Ενεργή βάρδια από {st:%d/%m/%Y %H:%M}\n{name}"
            if pending: text += f"\nΑναμονή επιβεβαίωσης: {pending}"
            self.shift_status.setText(text)
            self.start_shift_btn.setEnabled(False)
            self.end_shift_btn.setEnabled(bool(p))

        def _check_shift_updates(self):
            if not self.store: return
            shift=self.store.sync_active_shift()
            if not shift:
                if self._last_shift_signature != "NO_SHIFT":
                    self._last_shift_signature = "NO_SHIFT"
                    self._refresh_shift_status()
                return
            signature=json.dumps({
                "approved":shift.get("approved",[]),
                "excluded":shift.get("excluded",[]),
                "pending":shift.get("pending",[])
            },ensure_ascii=False,sort_keys=True)
            if signature!=self._last_shift_signature:
                self._last_shift_signature=signature
                self._refresh_shift_status()
            if shift.get("pending") and not self._pending_prompt_active:
                self._resolve_pending_members()

        def _live_map(self):
            if not self.store:
                QMessageBox.warning(self,"Έλεγχος","Δεν είναι διαθέσιμος ο φάκελος δεδομένων."); return
            LiveMapDialog(self.store,self).exec()

        def _shift_admin(self):
            pass

        def _backup(self):
            if not self.store:
                QMessageBox.warning(self, "Backup", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            try:
                path = self.store.backup_data()
                QMessageBox.information(self, "Backup", f"Το αντίγραφο ασφαλείας δημιουργήθηκε:\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Backup", str(exc))

        def _audit_view(self):
            if not self.store:
                QMessageBox.warning(self, "Audit log", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            path = self.store.audit / "admin_audit.jsonl"
            if not path.exists():
                QMessageBox.information(self, "Ιστορικό ενεργειών", "Δεν υπάρχουν ακόμη καταγραφές ενεργειών.")
                return
            dlg = QDialog(self); dlg.setWindowTitle("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ - Ιστορικό ενεργειών"); dlg.resize(900, 600)
            lay = QVBoxLayout(dlg); browser = QTextBrowser(); browser.setStyleSheet("font-family:Consolas,monospace")
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            pretty=[]
            for line in lines:
                try:
                    r=json.loads(line); pretty.append(f"{r.get('timestamp','')} | {r.get('user','')}@{r.get('computer','')} | {r.get('action','')} | {json.dumps(r.get('details',{}),ensure_ascii=False)}")
                except Exception:
                    pretty.append(line)
            browser.setPlainText("\n".join(pretty)); lay.addWidget(browser); dlg.exec()

        def _admin(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
            try:
                self.store.log_admin_action("OFFICER_DUTY_PANEL_OPENED")
            except Exception:
                pass
            dlg = QDialog(self); dlg.setWindowTitle("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ"); dlg.resize(720, 620)
            t = THEME_DARK if _clean(self.config.theme).lower() == "dark" else THEME_LIGHT
            dlg.setStyleSheet(_theme_stylesheet(self.config.theme))
            lay = QVBoxLayout(dlg); lay.setContentsMargins(24,22,24,22); lay.setSpacing(10)
            header = QLabel("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ"); header.setStyleSheet(f"font-size:20px;font-weight:900;color:{t['text']}")
            lay.addWidget(header)
            officer_agms = QLineEdit(); officer_agms.setPlaceholderText("Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας")
            officer_name = QLabel("—"); officer_name.setStyleSheet("font-weight:800;font-size:15px")
            form = QFormLayout(); form.addRow("Α.Γ.Μ.Σ.", officer_agms); form.addRow("Αξιωματικός", officer_name); lay.addLayout(form)
            status = QLabel(""); status.setWordWrap(True); status.setStyleSheet(
                f"background:{t['card2']};color:{t['text']};border:1px solid {t['border']};border-radius:10px;padding:9px;font-weight:700"
            )
            lay.addWidget(status)
            members = QListWidget(); lay.addWidget(members, 1)
            row = QHBoxLayout()
            accept_btn = QPushButton("ΑΠΟΔΟΧΗ"); exclude_btn = QPushButton("ΕΞΑΙΡΕΣΗ"); refresh_btn = QPushButton("ΑΝΑΝΕΩΣΗ")
            row.addWidget(accept_btn); row.addWidget(exclude_btn); row.addWidget(refresh_btn); lay.addLayout(row)
            row2 = QHBoxLayout()
            start_shift = QPushButton("ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ"); end_shift = QPushButton("ΛΗΞΗ ΒΑΡΔΙΑΣ"); live = QPushButton("ΖΩΝΤΑΝΗ ΕΙΚΟΝΑ")
            start_shift.setMinimumHeight(48); end_shift.setMinimumHeight(48)
            row2.addWidget(start_shift); row2.addWidget(end_shift); row2.addWidget(live); lay.addLayout(row2)

            def selected_officer():
                return self._people_by_agms.get(_clean(officer_agms.text()))

            def officer_changed(*_):
                p = selected_officer()
                officer_name.setText(_clean(f"{p.rank} {p.full_name}") if p else "—")

            def refresh_members():
                shift = self.store.sync_active_shift() if self.store else None
                members.clear()
                if not shift:
                    status.setText("Δεν υπάρχει ενεργή βάρδια.")
                    accept_btn.setEnabled(False); exclude_btn.setEnabled(False); end_shift.setEnabled(False); start_shift.setEnabled(True)
                    return
                start_shift.setEnabled(False); end_shift.setEnabled(True); accept_btn.setEnabled(True); exclude_btn.setEnabled(True)
                st = datetime.fromisoformat(shift["start_at"])
                off = shift.get("start_officer") or {}
                status.setText(f"Ενεργή βάρδια από {st:%d/%m/%Y %H:%M} — Αξιωματικός: {_clean(f"{off.get('rank','')} {off.get('full_name','')}")}")
                for state_key, label in (("approved", "ΑΠΟΔΕΚΤΟΣ"), ("pending", "ΑΝΑΜΟΝΗ"), ("excluded", "ΕΞΑΙΡΕΣΗ")):
                    for agms in shift.get(state_key, []):
                        person = self._people_by_agms.get(_clean(agms))
                        name = _clean(f"{person.rank} {person.full_name}") if person else f"ΑΓΜΣ {agms}"
                        members.addItem(f"{label} | {agms} | {name}")
                        item = members.item(members.count()-1); item.setData(Qt.UserRole, _clean(agms))

            def change_state(state):
                item = members.currentItem()
                if not item:
                    QMessageBox.warning(dlg, "Έλεγχος", "Επιλέξτε πρώτα άτομο."); return
                if state == "EXCLUDED":
                    agms = _clean(item.data(Qt.UserRole))
                    person = self._people_by_agms.get(agms)
                    name = _clean(f"{person.rank} {person.full_name}") if person else f"ΑΓΜΣ {agms}"
                    confirm = QMessageBox.question(
                        dlg,
                        "Επιβεβαίωση εξαίρεσης",
                        f"{name}\n\nΕίστε βέβαιοι ότι θέλετε να ΕΞΑΙΡΕΣΕΤΕ το άτομο από τη βάρδια;",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if confirm != QMessageBox.Yes:
                        return
                try:
                    self.store.set_shift_member_state(item.data(Qt.UserRole), state); refresh_members()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Βάρδια", str(exc))

            def do_start():
                p = selected_officer()
                if not p:
                    QMessageBox.warning(dlg, "Έλεγχος", "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
                try:
                    shift = self.store.start_officer_shift(p)
                    QMessageBox.information(dlg, "Βάρδια", f"Έναρξη βάρδιας {shift['start_at'].replace('T',' ')}.\nΕλέγξτε τους ΑΠΟΔΕΚΤΟΥΣ και εξαιρέστε όποιον ανήκει στην προηγούμενη βάρδια.")
                    refresh_members()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Βάρδια", str(exc))

            def do_end():
                p = selected_officer()
                if not p:
                    QMessageBox.warning(dlg, "Έλεγχος", "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
                try:
                    shift = self.store.end_officer_shift(p)
                    archive = archive_shift_docx(self.store, shift, self._people_by_agms)
                    current = create_shift_docx(self.store, shift, self._people_by_agms)
                    QMessageBox.information(dlg, "Λήξη βάρδιας", f"Η βάρδια ολοκληρώθηκε.\nΑρχειοθετήθηκε: {archive}")
                    refresh_members()
                    _open_path(current)
                except Exception as exc:
                    QMessageBox.critical(dlg, "Λήξη βάρδιας", str(exc))

            officer_agms.textChanged.connect(officer_changed)
            accept_btn.clicked.connect(lambda: change_state("APPROVED")); exclude_btn.clicked.connect(lambda: change_state("EXCLUDED")); refresh_btn.clicked.connect(refresh_members)
            start_shift.clicked.connect(do_start); end_shift.clicked.connect(do_end); live.clicked.connect(self._live_map)
            timer = QTimer(dlg); timer.timeout.connect(refresh_members); timer.start(2500)
            refresh_members(); dlg.exec()

        def _live_map(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            LiveMapDialog(self.store, self).exec()

        def _shift_admin(self):
            self._admin()

        def _add_position(self):
            value, ok = QInputDialog.getText(self, "Νέα θέση", "Ονομασία / αριθμός θέσης")
            value = _clean(value)
            if ok and value:
                existing = [self.position.itemText(i) for i in range(self.position.count())]
                if value not in existing: self.position.addItem(value)
                self.position.setCurrentText(value); self._save_config()

        def _report(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
            shift = self.store.sync_active_shift()
            if not shift:
                QMessageBox.information(self, "Τρέχον έντυπο", "Δεν υπάρχει ενεργή βάρδια."); return
            try:
                path = create_shift_docx(self.store, shift, self._people_by_agms)
                _open_path(path)
            except Exception as exc:
                QMessageBox.critical(self, "Word", str(exc))

        def _open_files(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
            try:
                _open_path(self.store.archive)
            except Exception as exc:
                QMessageBox.critical(self, "Αρχεία", str(exc))

        def _report_archive(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime.")
                return
            shifts = [s for s in self.store.list_shifts() if _clean(s.get("status")).upper() == "FINALIZED" and _clean(s.get("end_at"))]
            dlg = QDialog(self); dlg.setWindowTitle("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ ΒΑΡΔΙΑΣ"); dlg.resize(780, 560)
            lay = QVBoxLayout(dlg); lay.setContentsMargins(20,18,20,18); lay.setSpacing(10)
            title = QLabel("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ ΒΑΡΔΙΑΣ"); title.setStyleSheet("font-size:18px;font-weight:900")
            lay.addWidget(title)
            listing = QListWidget()
            for shift in shifts:
                item = QListWidgetItem(shift_report_title(shift))
                item.setData(Qt.UserRole, _clean(shift.get("shift_id")))
                listing.addItem(item)
            lay.addWidget(listing, 1)
            info = QLabel(f"Συνολικές ολοκληρωμένες βάρδιες: {len(shifts)}")
            lay.addWidget(info)
            buttons = QHBoxLayout()
            open_btn = QPushButton("ΑΝΟΙΓΜΑ ΑΝΑΦΟΡΑΣ")
            folder_btn = QPushButton("ΑΝΟΙΓΜΑ ΦΑΚΕΛΟΥ")
            close_btn = QPushButton("ΚΛΕΙΣΙΜΟ")
            buttons.addWidget(open_btn); buttons.addWidget(folder_btn); buttons.addStretch(); buttons.addWidget(close_btn)
            lay.addLayout(buttons)

            def selected_shift():
                item = listing.currentItem()
                if not item:
                    return None
                sid = _clean(item.data(Qt.UserRole))
                return next((s for s in shifts if _clean(s.get("shift_id")) == sid), None)

            def open_report():
                shift = selected_shift()
                if not shift:
                    QMessageBox.warning(dlg, "Αναφορές", "Επιλέξτε πρώτα μία βάρδια.")
                    return
                try:
                    path = archive_shift_docx(self.store, shift, self._people_by_agms)
                    _open_path(path)
                except Exception as exc:
                    QMessageBox.critical(dlg, "Αναφορές", str(exc))

            open_btn.clicked.connect(open_report)
            listing.itemDoubleClicked.connect(lambda *_: open_report())
            folder_btn.clicked.connect(lambda: _open_path(self.store.archive))
            close_btn.clicked.connect(dlg.accept)
            dlg.exec()

        def _personnel_history(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime.")
                return
            pin, ok = QInputDialog.getText(self, "Ιστορικό προσωπικού", "Κωδικός πρόσβασης", QLineEdit.Password)
            if not ok:
                return
            if hashlib.sha256(_clean(pin).encode("utf-8")).hexdigest() != STATISTICS_PIN_SHA256:
                QMessageBox.warning(self, "Ιστορικό προσωπικού", "Λανθασμένος κωδικός.")
                return

            dlg = QDialog(self); dlg.setWindowTitle("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ"); dlg.resize(1100, 720)
            lay = QVBoxLayout(dlg); lay.setContentsMargins(20,18,20,18); lay.setSpacing(10)
            title = QLabel("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ"); title.setStyleSheet("font-size:18px;font-weight:900")
            lay.addWidget(title)

            form = QFormLayout()
            person_edit = QLineEdit(); person_edit.setPlaceholderText("ΑΓΜΣ, επώνυμο ή όνομα — αρκεί και μόνο αυτό")
            from_edit = QLineEdit(); from_edit.setPlaceholderText("π.χ. 01/10/2026 (προαιρετικό)")
            to_edit = QLineEdit(); to_edit.setPlaceholderText("π.χ. 31/10/2026 (προαιρετικό)")
            position_combo = QComboBox(); position_combo.addItem("ΟΛΕΣ")
            for pos in self.config.positions or []:
                if _clean(pos):
                    position_combo.addItem(_clean(pos))
            direction_combo = QComboBox(); direction_combo.addItems(["ΟΛΑ", "ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"])
            form.addRow("Άτομο", person_edit)
            form.addRow("Από ημερομηνία", from_edit)
            form.addRow("Έως ημερομηνία", to_edit)
            form.addRow("Θέση", position_combo)
            form.addRow("Κατεύθυνση", direction_combo)
            lay.addLayout(form)

            actions = QHBoxLayout()
            search_btn = QPushButton("ΑΝΑΖΗΤΗΣΗ")
            clear_btn = QPushButton("ΚΑΘΑΡΙΣΜΟΣ")
            actions.addWidget(search_btn); actions.addWidget(clear_btn); actions.addStretch()
            lay.addLayout(actions)

            result_label = QLabel("Συμπληρώστε ένα ή περισσότερα κριτήρια.")
            lay.addWidget(result_label)
            table = QTableWidget(0, 8)
            table.setHorizontalHeaderLabels(["ΗΜΕΡΟΜΗΝΙΑ", "ΑΓΜΣ", "ΟΝΟΜΑ", "ΘΕΣΗ", "ΚΑΤΕΥΘΥΝΣΗ", "ΕΝΑΡΞΗ", "ΛΗΞΗ", "ΔΙΑΡΚΕΙΑ"])
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(table, 1)

            def norm(value):
                raw = _clean(value).upper()
                raw = "".join(ch for ch in unicodedata.normalize("NFD", raw) if unicodedata.category(ch) != "Mn")
                return re.sub(r"\s+", " ", raw)

            def parse_date(value):
                value = _clean(value)
                if not value:
                    return None
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(value, fmt).date()
                    except ValueError:
                        pass
                raise ValueError(f"Μη έγκυρη ημερομηνία: {value}")

            def do_search():
                query = norm(person_edit.text())
                pos = _clean(position_combo.currentText())
                direction = _clean(direction_combo.currentText()).upper()
                if not query and not _clean(from_edit.text()) and not _clean(to_edit.text()) and pos == "ΟΛΕΣ" and direction == "ΟΛΑ":
                    QMessageBox.warning(dlg, "Ιστορικό", "Συμπληρώστε τουλάχιστον ένα κριτήριο.")
                    return
                try:
                    date_from = parse_date(from_edit.text())
                    date_to = parse_date(to_edit.text())
                except ValueError as exc:
                    QMessageBox.warning(dlg, "Ιστορικό", str(exc))
                    return
                if date_from and date_to and date_from > date_to:
                    QMessageBox.warning(dlg, "Ιστορικό", "Η ημερομηνία «Από» είναι μετά την ημερομηνία «Έως».")
                    return

                rows = []
                for session in self.store.completed_sessions_all():
                    st = session["start"]
                    sdt = session["start_dt"]; edt = session["end_dt"]
                    agms = _clean(st.get("agms"))
                    person = self._people_by_agms.get(agms)
                    if person:
                        name = _clean(f"{person.rank} {person.surname} {person.given_name}")
                        hay = norm(f"{person.agms} {person.rank} {person.surname} {person.given_name} {person.full_name}")
                    else:
                        name = _clean(f"{st.get('rank','')} {st.get('full_name','')}")
                        hay = norm(f"{agms} {name}")
                    if query and query not in hay:
                        continue
                    if date_from and sdt.date() < date_from:
                        continue
                    if date_to and sdt.date() > date_to:
                        continue
                    position = _clean(st.get("position"))
                    item_direction = _clean(st.get("direction")).upper()
                    if pos != "ΟΛΕΣ" and position != pos:
                        continue
                    if direction != "ΟΛΑ" and item_direction != direction:
                        continue
                    minutes = max(0, int((edt - sdt).total_seconds() // 60))
                    hours, mins = divmod(minutes, 60)
                    rows.append((sdt, [
                        sdt.strftime("%d/%m/%Y"), agms, name, position, item_direction,
                        sdt.strftime("%H:%M"), edt.strftime("%H:%M"), f"{hours:02d}:{mins:02d}"
                    ]))

                rows.sort(key=lambda x: x[0], reverse=True)
                table.setRowCount(len(rows))
                for r, (_, values) in enumerate(rows):
                    for col, value in enumerate(values):
                        table.setItem(r, col, QTableWidgetItem(str(value)))
                result_label.setText(f"Βρέθηκαν {len(rows)} καταχωρίσεις.")
                try:
                    self.store.log_admin_action("PERSONNEL_HISTORY_SEARCH", {
                        "query": _clean(person_edit.text()), "from": _clean(from_edit.text()), "to": _clean(to_edit.text()),
                        "position": pos, "direction": direction, "results": len(rows)
                    })
                except Exception:
                    pass

            def clear_search():
                person_edit.clear(); from_edit.clear(); to_edit.clear()
                position_combo.setCurrentIndex(0); direction_combo.setCurrentIndex(0)
                table.setRowCount(0); result_label.setText("Συμπληρώστε ένα ή περισσότερα κριτήρια.")

            search_btn.clicked.connect(do_search)
            clear_btn.clicked.connect(clear_search)
            person_edit.returnPressed.connect(do_search)
            dlg.exec()

        def _snapshot(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Ορίστε κεντρικό φάκελο."); return
            active = self.store.active_all()
            if not active:
                QMessageBox.information(self,"Στιγμιαία εικόνα","Δεν υπάρχουν ανοικτές θέσεις."); return
            lines = [f"{x.get('rank','')} {x.get('full_name','')} — Θ. {x.get('position','')} {x.get('direction','')} — από {x.get('timestamp','').replace('T',' ')}" for x in active]
            QMessageBox.information(self,"Στιγμιαία εικόνα","\n".join(lines))


    app = QApplication(list(args or sys.argv))
    app.setApplicationName("TDE Position Tracking")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())

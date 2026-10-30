"""Officer shift lifecycle, approvals, member transitions and finalization guards."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import os
import socket
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord
from position_tracking_store_io import BusyError


class ShiftLifecycleMixin:
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
        existing = self.get_shift(shift_id)
        if existing and _clean(existing.get("status")).upper() == "FINALIZED":
            raise ValueError("Η βάρδια έχει οριστικοποιηθεί και δεν μπορεί να αντικατασταθεί.")
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
        self._store_shift_snapshot(data)
        self.log_admin_action("SHIFT_SAVED", {"shift_id": shift_id, "people": len(unique), "lookback_minutes": lookback})
        return data


    def _current_shift_path(self) -> Path:
        return self.shifts / "CURRENT_SHIFT.json"


    def current_shift(self) -> dict | None:
        path = self._current_shift_path()
        if not self.shifts.is_dir():
            raise BusyError("Ο κοινός φάκελος βαρδιών δεν είναι διαθέσιμος.")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if _clean(data.get("status")).upper() == "ACTIVE" else None
        except FileNotFoundError:
            return None
        except Exception as exc:
            # A read failure is not proof that no shift exists.
            raise BusyError(f"Δεν είναι ασφαλής η ανάγνωση τρέχουσας βάρδιας: {exc}") from exc


    def current_report_shift(self) -> dict | None:
        """Return the active/last shift; finalized history itself lives in SQLite."""
        path = self._current_shift_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if _clean(data.get("shift_id")) and _clean(data.get("status")).upper() in {"ACTIVE", "FINALIZED"}:
                return data
        except Exception:
            pass
        shift_id = self._current_report_shift_id()
        if shift_id:
            data = self.get_shift(shift_id)
            if data and _clean(data.get("status")).upper() == "FINALIZED":
                return data
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
        with self.officer_lock("__SHIFT_CONTROL__", timeout=20.0):
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
                    if agms and agms not in seen:
                        approved.append(agms); seen.add(agms)
                excluded = []
                for value in initial_excluded or []:
                    agms = _clean(value)
                    if agms and agms not in seen:
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


    def _sync_active_shift_locked(self) -> dict | None:
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
        # A person may explicitly END before the officer next refreshes. Their
        # durable work must still be offered for the membership decision.
        for row in self._position_rows("""SELECT DISTINCT agms FROM position_operations
                WHERE kind='START' AND state='COMMITTED'
                AND json_extract(payload, '$.timestamp')>=?""", (shift['start_at'],)):
            agms = row['agms']
            if agms not in known:
                pending.append(agms); known.add(agms); changed = True
        if changed:
            shift["pending"] = pending
            shift["updated_at"] = datetime.now().isoformat(timespec="seconds")
            self._atomic_json(self._current_shift_path(), shift)
        return shift


    def sync_active_shift(self) -> dict | None:
        with self.officer_lock("__SHIFT_CONTROL__", timeout=20.0):
            return self._sync_active_shift_locked()


    def set_shift_member_state(self, agms: str, state: str, expected_shift_id: str = '') -> dict:
        with self.officer_lock("__SHIFT_CONTROL__", timeout=20.0):
            shift = self.current_shift()
            if not shift:
                raise ValueError("Δεν υπάρχει ενεργή βάρδια.")
            if expected_shift_id and shift['shift_id'] != expected_shift_id:
                raise BusyError('Η βάρδια άλλαξε. Ελέγξτε ξανά πριν από αλλαγή συμμετοχής.')
            agms = _clean(agms)
            if not agms:
                raise ValueError('Απαιτείται ΑΓΜΣ μέλους βάρδιας.')
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


    def end_officer_shift_member(
        self, officer: PersonnelRecord, agms: str, expected_shift_id: str,
        expected_start_event_id: str,
    ) -> dict:
        """Individually end a confirmed, approved member without finalizing shift."""
        agms = _clean(agms)
        if not agms or not expected_start_event_id:
            raise BusyError("Η επιλεγμένη θέση δεν έχει έγκυρο αναγνωριστικό.")
        with self.officer_lock("__SHIFT_CONTROL__", timeout=20.0):
            shift = self.current_shift()
            if not shift or _clean(shift.get("shift_id")) != _clean(expected_shift_id):
                raise BusyError("Η βάρδια άλλαξε. Ελέγξτε ξανά την τρέχουσα λίστα.")
            if agms not in {_clean(x) for x in shift.get("approved", [])}:
                raise BusyError("Ο αστυνομικός δεν ανήκει πλέον στους αποδεκτούς της βάρδιας.")
            active = self.get_active(agms)
            if not active or _clean(active.get("event_id")) != _clean(expected_start_event_id):
                raise BusyError("Η ενεργή θέση άλλαξε. Δεν καταχωρίστηκε λανθασμένη λήξη.")
            member = PersonnelRecord(
                agms=agms, rank=_clean(active.get("rank")),
                surname=_clean(active.get("surname")), given_name=_clean(active.get("given_name")),
            )
            event = self.end(
                member, expected_start_event_id=expected_start_event_id,
                end_reason="SHIFT_SINGLE_BY_OFFICER", end_officer=officer,
            )
            try:
                self.log_admin_action("SHIFT_SINGLE_END_POSITION", {
                    "shift_id": expected_shift_id, "officer_agms": officer.agms,
                    "member_agms": agms, "position": _clean(active.get("position")),
                    "start_event_id": expected_start_event_id,
                    "end_event_id": _clean(event.get("event_id")),
                })
            except Exception:
                # Audit actor and reason are also embedded in durable END event.
                pass
            return event


    def end_officer_shift(
        self, officer: PersonnelRecord, when: datetime | None = None,
        expected_active_start_ids: dict[str, str] | None = None,
        expected_shift_id: str = "",
    ) -> dict:
        with self.officer_lock("__SHIFT_CONTROL__", timeout=20.0):
            shift = self._sync_active_shift_locked()
            if not shift:
                raise ValueError("Δεν υπάρχει ενεργή βάρδια.")
            if expected_shift_id and _clean(shift.get("shift_id")) != _clean(expected_shift_id):
                raise BusyError("Η βάρδια άλλαξε. Ανανεώστε τη λίστα πριν συνεχίσετε.")
            if shift.get("pending"):
                raise ValueError("Υπάρχουν άτομα σε ΑΝΑΜΟΝΗ. Κάντε πρώτα ΑΠΟΔΟΧΗ ή ΕΞΑΙΡΕΣΗ.")
            when = when or datetime.now()
            if when < datetime.fromisoformat(shift['start_at']):
                raise ValueError('Η λήξη βάρδιας προηγείται της έναρξής της.')
            # A shift is a report/membership boundary, never a physical END.
            # Retain the old argument for callers; a live-position preview no
            # longer constrains finalization because no live record is mutated.
            shift["closed_active_agms"] = []
            shift["status"] = "FINALIZED"
            shift["end_at"] = when.isoformat(timespec="seconds")
            shift["end_officer"] = self._person_payload(officer)
            shift["finalized_at"] = datetime.now().isoformat(timespec="seconds")
            # Το ιστορικό βαρδιών αποθηκεύεται σε SQLite. Το CURRENT_SHIFT.json
            # μένει μόνο ως ελαφρύ ζωντανό αρχείο συγχρονισμού μεταξύ σταθμών.
            # Persist the finalized report before replacing CURRENT_SHIFT.
            # If SQLite is unavailable, the shift remains ACTIVE and retryable.
            self._store_shift_snapshot(shift, make_current_report=True)
            self._atomic_json(self._current_shift_path(), shift)
            self.log_admin_action("SHIFT_ENDED", {"shift_id": shift["shift_id"], "officer_agms": officer.agms, "approved": len(shift.get("approved", [])), "excluded": len(shift.get("excluded", []))})
            return shift


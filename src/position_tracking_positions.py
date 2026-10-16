"""Position START/END receipts, idempotent replay, corrections and account handoff."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import json
import os
import socket
import uuid
from position_tracking_common import _clean, _safe_name
from position_tracking_personnel import PersonnelRecord
from position_tracking_store_io import BusyError
from position_tracking_handoff import close_previous_windows_user_positions


class PositionStoreMixin:
    def _effective_start_timestamp(self, event_id: str, timestamp: str) -> str:
        path = self.corrections / f"{_safe_name(event_id)}.json"
        if not path.is_file():
            return timestamp
        data = json.loads(path.read_text(encoding="utf-8"))
        if _clean(data.get("start_event_id")) != _clean(event_id):
            raise BusyError("Ασυμφωνία στα στοιχεία διόρθωσης ώρας.")
        return _clean(data["corrected_start_at"])


    def _apply_start_correction(self, event: dict) -> dict:
        if _clean(event.get("kind")).upper() != "START":
            return event
        revised = self._effective_start_timestamp(_clean(event.get("event_id")), _clean(event.get("timestamp")))
        if revised == _clean(event.get("timestamp")):
            return event
        result = dict(event)
        result["original_timestamp"] = event["timestamp"]
        result["timestamp"] = revised
        return result


    def correct_active_start(self, agms: str, new_when: datetime, officer: PersonnelRecord, reason: str) -> dict:
        """Audited logical correction; immutable raw START event remains intact."""
        reason = _clean(reason)
        if len(reason) < 5:
            raise ValueError("Συμπληρώστε αιτιολογία τουλάχιστον 5 χαρακτήρων.")
        if new_when > datetime.now():
            raise ValueError("Δεν επιτρέπεται μελλοντική ώρα έναρξης.")
        with self.officer_lock(agms):
            active = self.get_active(agms)
            if not active:
                raise ValueError("Η θέση έχει ήδη κλείσει ή δεν υπάρχει.")
            old_when = datetime.fromisoformat(active["timestamp"])
            if new_when.date() != old_when.date():
                raise ValueError("Για ασφάλεια, η διόρθωση περιορίζεται στην ίδια ημερομηνία.")
            event_id = _clean(active.get("event_id"))
            if not event_id:
                raise ValueError("Δεν βρέθηκε αναγνωριστικό έναρξης.")
            correction = {
                "start_event_id": event_id, "agms": agms,
                "previous_start_at": active["timestamp"],
                "corrected_start_at": new_when.isoformat(timespec="seconds"),
                "corrected_by": self._person_payload(officer),
                "reason": reason,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
            }
            path = self.corrections / f"{_safe_name(event_id)}.json"
            if path.exists():
                previous = json.loads(path.read_text(encoding="utf-8"))
                correction["original_start_at"] = previous.get("original_start_at", previous.get("previous_start_at"))
            else:
                correction["original_start_at"] = active["timestamp"]
            self._atomic_json(path, correction)
            self.log_admin_action("ACTIVE_START_TIME_CORRECTED", correction)
            return correction


    def get_active(self, agms: str) -> dict | None:
        path = self._active_path(agms)
        if not self.active.is_dir():
            raise BusyError("Ο κοινός φάκελος ενεργών θέσεων δεν είναι διαθέσιμος.")
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
            return None if self._has_end_receipt(item) else self._apply_start_correction(item)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            # Fail closed: an unreadable shared active file is NOT a free booth.
            raise BusyError(f"Δεν είναι ασφαλής η ανάγνωση ενεργής θέσης {agms}: {exc}") from exc


    def _existing_operation_event(self, op_id: str, when: datetime) -> dict | None:
        if not op_id:
            return None
        # A retry after a server acknowledgement was lost must never record
        # another START/END. Shared lock for AGMS protects this lookup.
        folder = self.events / f"{when:%Y}" / f"{when:%m}" / f"{when:%Y-%m-%d}"
        prefix = f"{when:%Y%m%d_%H%M%S}_"
        for path in folder.glob(f"{prefix}*_{_safe_name(op_id)}.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("event_id") == op_id:
                    return data
            except (OSError, ValueError):
                raise BusyError("Δεν διαβάζεται η προηγούμενη καταχώριση συγχρονισμού.")
        return None


    def _write_event(self, event: dict) -> Path:
        dt = datetime.fromisoformat(event["timestamp"])
        folder = self.events / f"{dt:%Y}" / f"{dt:%m}" / f"{dt:%Y-%m-%d}"
        filename = f"{dt:%Y%m%d_%H%M%S_%f}_{event['event_id']}.json"
        path = folder / filename
        self._atomic_json(path, event)
        return path


    def start(self, person: PersonnelRecord, position: str, direction: str, when: datetime | None = None, client_id: str = "", event_id: str = "", origin_computer: str = "", origin_user: str = "") -> dict:
        when = when or datetime.now()
        position = _clean(position)
        direction = _clean(direction).upper()
        if not position:
            raise ValueError("Επιλέξτε θέση.")
        if direction not in {"ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"}:
            raise ValueError("Επιλέξτε κατεύθυνση ΕΙΣΟΔΟΣ ή ΕΞΟΔΟΣ.")
        with self.officer_lock(person.agms):
            previous = self._existing_operation_event(event_id, when)
            if previous:
                if previous.get("kind") != "START" or previous.get("agms") != person.agms:
                    raise BusyError("Ασυμφωνία αναγνωριστικού START.")
                current = self.get_active(person.agms)
                if current and _clean(current.get("event_id")) == event_id:
                    return previous
                if current:
                    raise BusyError("Η παλιά έναρξη αντικαταστάθηκε. Δεν επιτρέπεται επανακατάληψη.")
                # If START was recorded but its active file was interrupted,
                # recover only if the original shift was never ended.
                if self._has_end_receipt(previous):
                    return previous
                with self._shift_db_connect() as db:
                    closed = db.execute(
                        "SELECT 1 FROM personnel_sessions WHERE start_event_id=? LIMIT 1", (event_id,)
                    ).fetchone()
                if closed:
                    return previous
                with self.officer_lock("__POSITION_START__"):
                    if any(_clean(x.get("position")) == position for x in self.active_all()):
                        raise BusyError("Η θέση έχει ήδη καταληφθεί στο μεταξύ.")
                    self._atomic_json(self._active_path(person.agms), previous)
                return previous
            # Serialize START operations across all stations so two PCs cannot
            # claim the same physical position at the same moment.
            with self.officer_lock("__POSITION_START__"):
                current = self.get_active(person.agms)
                if current and event_id and current.get("event_id") == event_id:
                    return current
                if current:
                    raise ValueError(
                        f"Υπάρχει ήδη ανοικτή θέση για {person.full_name}: "
                        f"{current.get('position','')} {current.get('direction','')} από {current.get('timestamp','')}. "
                        "Πρέπει πρώτα να γίνει ΛΗΞΗ."
                    )
                occupied = next(
                    (
                        item for item in self.active_all()
                        if _clean(item.get("position")) == position
                        and _clean(item.get("agms")) != _clean(person.agms)
                    ),
                    None,
                )
                if occupied:
                    occupant = _clean(
                        f"{occupied.get('rank','')} {occupied.get('surname','')} {occupied.get('given_name','')}"
                    ) or _clean(occupied.get("full_name")) or _clean(occupied.get("agms"))
                    raise ValueError(
                        f"Η ΘΕΣΗ {position} χρησιμοποιείται ήδη από {occupant}. "
                        "Πρέπει πρώτα να γίνει ΛΗΞΗ της ενεργής θέσης."
                    )
                event = {
                    "version": 2,
                    "event_id": event_id or uuid.uuid4().hex,
                    "kind": "START",
                    "timestamp": when.isoformat(timespec="seconds"),
                    "agms": person.agms,
                    "rank": person.rank,
                    "surname": person.surname,
                    "given_name": person.given_name,
                    "full_name": person.full_name,
                    "position": position,
                    "direction": direction,
                    "computer": origin_computer or socket.gethostname(),
                    "user": origin_user or os.environ.get("USERNAME") or os.environ.get("USER") or "",
                    "client_id": _clean(client_id),
                }
                path = self._write_event(event)
                event["event_file"] = str(path)
                try:
                    self._atomic_json(self._active_path(person.agms), event)
                except Exception:
                    # SMB can commit replace() and lose its acknowledgement.
                    # Never erase the durable START when a marker exists, or
                    # when its state cannot be read safely. The original ID
                    # lets a pending offline operation reconcile on retry.
                    try:
                        self._active_path(person.agms).read_text(encoding="utf-8")
                    except FileNotFoundError:
                        try:
                            if self.active.is_dir():
                                # Confirmed pre-commit failure: retain the old
                                # guarantee that no phantom START is reported.
                                path.unlink(missing_ok=True)
                        except OSError:
                            pass  # uncertain share state: preserve evidence
                    except OSError:
                        pass
                    raise
        try:
            self.sync_active_shift()
        except Exception:
            # START was durably recorded. Do not report its failure merely
            # because synchronizing the shift membership is delayed.
            pass
        return event


    def end(self, person: PersonnelRecord, when: datetime | None = None, expected_start_event_id: str = "", end_reason: str = "", end_officer: PersonnelRecord | None = None, event_id: str = "", origin_computer: str = "", origin_user: str = "") -> dict:
        when = when or datetime.now()
        with self.officer_lock(person.agms):
            previous = self._existing_operation_event(event_id, when)
            if previous:
                if previous.get("kind") != "END" or previous.get("agms") != person.agms:
                    raise BusyError("Ασυμφωνία αναγνωριστικού END.")
                current = self.get_active(person.agms)
                if current and _clean(current.get("event_id")) == _clean(previous.get("start_event_id")):
                    # Repair interruption between END event and active release.
                    receipt = self.pending_index / f"{_safe_name(current.get('event_id'))}.json"
                    self._atomic_json(receipt, {"start": current, "end": previous})
                    self._active_path(person.agms).unlink(missing_ok=True)
                    try:
                        self._store_personnel_session(current, previous)
                    except Exception:
                        pass  # durable receipt is reconciled on subsequent startup
                    else:
                        receipt.unlink(missing_ok=True)
                elif current:
                    raise BusyError("Η θέση άλλαξε μετά την προηγούμενη ΛΗΞΗ.")
                return previous
            current = self.get_active(person.agms)
            if not current:
                raise ValueError(f"Δεν υπάρχει ανοικτή θέση για {person.full_name}.")
            if expected_start_event_id and _clean(current.get("event_id")) != _clean(expected_start_event_id):
                raise BusyError("Η θέση άλλαξε χρήστη πριν επιβεβαιωθεί η λήξη. Δεν τροποποιήθηκε η νέα καταχώριση.")
            event = {
                "version": 2,
                "event_id": event_id or uuid.uuid4().hex,
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
                "computer": origin_computer or socket.gethostname(),
                "user": origin_user or os.environ.get("USERNAME") or os.environ.get("USER") or "",
            }
            if end_reason:
                event["end_reason"] = _clean(end_reason)
            if end_officer:
                event["end_officer"] = self._person_payload(end_officer)
            self._write_event(event)
            # Durable receipt before releasing a booth; history indexing can be
            # retried later if SQLite is locked or temporarily unavailable.
            receipt = self.pending_index / f"{_safe_name(current.get('event_id'))}.json"
            self._atomic_json(receipt, {"start": current, "end": event})
            self._active_path(person.agms).unlink(missing_ok=True)
            try:
                self._store_personnel_session(current, event)
            except Exception:
                event["session_index_pending"] = True
            else:
                receipt.unlink(missing_ok=True)
            return event


    def active_all(self) -> list[dict]:
        if not self.active.is_dir():
            raise BusyError("Δεν είναι διαθέσιμος ο κοινός φάκελος ενεργών θέσεων.")
        result: list[dict] = []
        for path in sorted(self.active.glob("*.json")):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise BusyError(f"Δεν διαβάζεται η δέσμευση {path.name}: {exc}") from exc
            if not self._has_end_receipt(item):
                result.append(self._apply_start_correction(item))
        return sorted(result, key=lambda x: (_clean(x.get("direction")), _clean(x.get("position")), _clean(x.get("full_name"))))


    def close_previous_windows_user_positions(
        self, computer: str, windows_user: str, *, protected_start_ids=()
    ) -> list[dict]:
        return close_previous_windows_user_positions(
            self, computer, windows_user, PersonnelRecord, _clean, BusyError,
            protected_start_ids=protected_start_ids,
        )


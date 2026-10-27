"""Direct central operator requests. No local settings, outbox, replay or cache."""
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import uuid

from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord, PersonnelRepository
from position_tracking_store import SharedEventStore

UNCONFIRMED = "Δεν υπάρχει πρόσβαση στα κεντρικά δεδομένα — η καταχώριση δεν επιβεβαιώθηκε"


@dataclass(frozen=True)
class PositionRequest:
    kind: str
    agms: str
    position: str = ""
    direction: str = ""
    expected_start_id: str = ""
    operation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    when: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class PositionOutcome:
    status: str
    event: dict | None = None
    message: str = ""


class CentralOperator:
    def __init__(self, root: Path, personnel: Path):
        self.root = Path(root)
        self.personnel = Path(personnel)

    @classmethod
    def from_shared_directory(cls, directory: Path):
        directory = Path(directory)
        # Read the shared configuration as-is. Never invoke user-profile
        # settings migration or silently fall back to a local business store.
        settings = directory / ".tde_runtime" / "position_tracking.settings.json"
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except FileNotFoundError:
            directory.stat()
            data = {}
        root = Path(data.get("central_root") or directory / ".tde_runtime")
        if not root.is_absolute():
            root = directory / root
        candidates = [root / "personnel.xlsx"]
        for folder in (directory / "CONFIG", directory):
            candidates.extend(folder / name for name in (
                "ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"))
        personnel = next((path for path in candidates if path.is_file()), candidates[0])
        return cls(root, personnel)

    def _store(self):
        # The configured share root must already exist. A disappeared share
        # must never cause a new fallback directory/database to be created.
        if not self.root.is_dir():
            raise OSError(UNCONFIRMED)
        return SharedEventStore(self.root)

    def lookup(self, agms: str):
        store = self._store()
        agms = _clean(agms)
        active = store.get_active(agms) if agms else None
        if active:
            return self._active_person(active), active
        people = PersonnelRepository.load(self.personnel)
        person = next((person for person in people if person.agms == agms), None)
        return person, active

    @staticmethod
    def _active_person(active):
        return PersonnelRecord(active["agms"], active.get("rank", ""),
                               active.get("surname", ""), active.get("given_name", ""))

    def check(self, request: PositionRequest):
        # Constructor recovery obtains the same mutation lock as the writer.
        # This is only called after the caller's original worker has finished.
        store = self._store()
        with store.officer_lock("__POSITION_TRANSACTIONS__"):
            store._recover_position_operations_locked()
            event = store._committed_position_operation(request.operation_id)
        if event:
            if event["kind"] != request.kind or event["agms"] != request.agms:
                raise ValueError("Ασυμφωνία αναγνωριστικού καταχώρισης.")
            if request.kind == "START" and (event["position"] != request.position or event["direction"] != request.direction):
                raise ValueError("Το αναγνωριστικό αφορά διαφορετική θέση ή κατεύθυνση.")
            if request.kind == "END" and event["start_event_id"] != request.expected_start_id:
                raise ValueError("Το αναγνωριστικό αφορά διαφορετική ΕΝΑΡΞΗ.")
            return PositionOutcome("CONFIRMED", event, "Η καταχώριση επιβεβαιώθηκε κεντρικά.")
        return PositionOutcome("NOT_COMMITTED", message="Δεν βρέθηκε επιβεβαιωμένη καταχώριση. Ελέγξτε την ενεργή θέση πριν από νέα ενέργεια.")

    def execute(self, request: PositionRequest):
        try:
            store = self._store()
            if request.kind == "START":
                if request.position not in {str(i) for i in range(1, 15)}:
                    raise ValueError("Επιλέξτε φυσική θέση 1 έως 14.")
                people = PersonnelRepository.load(self.personnel)
                person = next((person for person in people if person.agms == request.agms), None)
                if not person:
                    raise ValueError("Ο ΑΓΜΣ δεν βρέθηκε στην κεντρική λίστα προσωπικού.")
                event = store.start(person, request.position, request.direction,
                                    when=request.when, event_id=request.operation_id, sync_shift=False)
            elif request.kind == "END":
                if not request.expected_start_id:
                    raise ValueError("Ελέγξτε πρώτα την πραγματική ενεργή ΕΝΑΡΞΗ.")
                active = store.get_active(request.agms)
                if not active:
                    # Includes an original END which committed before losing ACK.
                    return self.check(request)
                event = store.end(self._active_person(active), when=request.when,
                                  event_id=request.operation_id, expected_start_event_id=request.expected_start_id)
            else:
                raise ValueError("Μη έγκυρη ενέργεια θέσης.")
            if event.get("superseded"):
                return self.check(request)
            return PositionOutcome("CONFIRMED", event, "Η καταχώριση επιβεβαιώθηκε κεντρικά.")
        except Exception as error:
            # No speculative failure or success. Read back the SAME ID, without
            # replaying another mutation, when the central store can be reached.
            try:
                outcome = self.check(request)
            except Exception:
                return PositionOutcome("UNKNOWN", message=UNCONFIRMED)
            if outcome.status == "CONFIRMED":
                return outcome
            message = str(error) if isinstance(error, ValueError) else outcome.message
            return PositionOutcome("NOT_COMMITTED", message=message)

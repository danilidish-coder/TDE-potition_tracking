"""Direct central operator requests. No local settings, outbox, replay or cache."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
import threading
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
    handover_start_id: str = ''


@dataclass(frozen=True)
class PositionOutcome:
    status: str
    event: dict | None = None
    message: str = ""


class CentralOperator:
    def __init__(self, root: Path, personnel: Path):
        self.root = Path(root)
        self.personnel = Path(personnel)
        # One store per process. Building SharedEventStore creates ~20
        # directories, opens the database, takes the GLOBAL position
        # transaction lock and runs recovery. Doing that for every keystroke
        # or mail poll of 15 stations over SMB starved real START/END writes.
        self._store_lock = threading.Lock()
        self._store_cache = None
        self._people_cache = None

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
        store = self._store_cache
        if store is None:
            with self._store_lock:
                if self._store_cache is None:
                    # A failed construction is not cached; the next call retries.
                    self._store_cache = SharedEventStore(self.root)
                store = self._store_cache
        return store

    def lookup(self, agms: str):
        store = self._store()
        # Read-only probe. The global lock is taken only when a crashed or
        # interrupted operation really needs recovery before it is shown.
        store.recover_if_needed()
        agms = _clean(agms)
        active = store.get_active(agms) if agms else None
        if active:
            return self._active_person(active), active
        people = self.people(store)
        person = next((person for person in people if person.agms == agms), None)
        return person, active

    def people(self, store):
        """Central personnel list, re-read only when the central document changes."""
        rows = store._position_rows("SELECT revision,payload FROM officer_documents WHERE document_key='personnel'")
        if rows:
            meta = json.loads(rows[0]['payload'])
            path = store.root / meta['path']
            revision = rows[0]['revision']
            key = ('central', str(path), meta['sha256'], revision)
            cached = self._people_cache
            if cached is not None and cached[0] == key:
                store._personnel_revision = revision
                return cached[1]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != meta['sha256']:
                raise OSError('Ασυμφωνία κεντρικής έκδοσης προσωπικού.')
            people = PersonnelRepository.load(data)
            store._personnel_revision = revision
        else:
            path = self.personnel
            info = path.stat()
            key = ('legacy', str(path), info.st_mtime_ns, info.st_size)
            cached = self._people_cache
            if cached is not None and cached[0] == key:
                store._personnel_revision = 'LEGACY_CENTRAL_WORKBOOK'
                return cached[1]
            people = PersonnelRepository.load(path)
            store._personnel_revision = 'LEGACY_CENTRAL_WORKBOOK'
        self._people_cache = (key, people)
        return people

    def communication(self, client_id, acknowledge=''):
        store = self._store()
        store.write_client_heartbeat(client_id)
        if acknowledge:
            store.acknowledge_message(acknowledge, client_id)
        messages = {m['message_id']: m for m in store.pending_messages(client_id)}
        for row in store._position_rows("SELECT payload FROM officer_documents WHERE document_key LIKE 'message:%'"):
            message = json.loads(row['payload'])
            ack = store.comm_acks / message['message_id'] / (client_id + '.json')
            if client_id in message['targets'] and not ack.exists():
                messages[message['message_id']] = message
        return sorted(messages.values(), key=lambda m: m['created_at'])

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
            if request.handover_start_id and event.get('handover', {}).get('previous_start_id') != request.handover_start_id:
                raise ValueError('Το αναγνωριστικό αφορά διαφορετική αντικατάσταση.')
            return PositionOutcome("CONFIRMED", event, "Η καταχώριση επιβεβαιώθηκε κεντρικά.")
        return PositionOutcome("NOT_COMMITTED", message="Δεν βρέθηκε επιβεβαιωμένη καταχώριση. Ελέγξτε την ενεργή θέση πριν από νέα ενέργεια.")

    def execute(self, request: PositionRequest):
        try:
            store = self._store()
            if store._committed_position_operation(request.operation_id):
                return self.check(request)
            if request.kind == "START":
                if request.position not in {str(i) for i in range(1, 15)}:
                    raise ValueError("Επιλέξτε φυσική θέση 1 έως 14.")
                people = self.people(store)
                person = next((person for person in people if person.agms == request.agms), None)
                if not person:
                    raise ValueError("Ο ΑΓΜΣ δεν βρέθηκε στην κεντρική λίστα προσωπικού.")
                if request.handover_start_id:
                    event = store.handover(person, request.position, request.direction,
                                           request.handover_start_id, request.operation_id, when=request.when)
                else:
                    claims = store._position_rows('SELECT agms FROM position_live WHERE position=?', (request.position,))
                    occupied = store._claim_event(claims[0]['agms']) if claims else None
                    if occupied and occupied['agms'] != person.agms:
                        return PositionOutcome('HANDOVER_REQUIRED', occupied, 'Απαιτείται επιβεβαίωση αντικατάστασης.')
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

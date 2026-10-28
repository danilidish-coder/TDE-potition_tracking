"""Simple central officer commands. AGMS is declared attribution, not identity."""
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
from pathlib import Path
import uuid

from position_tracking_central import CentralOperator, PositionOutcome, UNCONFIRMED
from position_tracking_officer_store import OfficerStore
from position_tracking_personnel import PersonnelRepository
from position_tracking_store_io import BusyError


@dataclass(frozen=True)
class OfficerRequest:
    action: str
    officer_agms: str
    values_json: str = '{}'
    confirmed: bool = False
    action_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    recorded_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec='microseconds'))
    workbook: bytes = b''

    @property
    def values(self):
        return json.loads(self.values_json)

    @property
    def intent(self):
        return dict(action=self.action, officer_agms=self.officer_agms, values=self.values,
                    workbook_sha256=hashlib.sha256(self.workbook).hexdigest() if self.workbook else '')


class CentralOfficer(CentralOperator):
    def _store(self):
        if not self.root.is_dir():
            raise OSError(UNCONFIRMED)
        return OfficerStore(self.root)

    def snapshot(self, officer_agms):
        store = self._store()
        people = self.people(store)
        officer = next((p for p in people if p.agms == officer_agms), None)
        if not officer:
            raise ValueError('Το δηλωμένο ΑΓΜΣ ΑΞΥΠ δεν υπάρχει στην κεντρική λίστα.')
        shift = store.current_shift()
        active = store.active_all()
        if shift:
            known = set(shift['approved'] + shift['excluded'] + shift['pending'])
            candidates = {a['agms'] for a in active} | {r['agms'] for r in store._position_rows(
                "SELECT DISTINCT agms FROM position_operations WHERE kind='START' AND state='COMMITTED' AND json_extract(payload,'$.timestamp')>=?", (shift['start_at'],))}
            shift['pending'] += sorted(candidates - known)
        roster = store.document('personnel')
        return dict(officer=officer, people=people, shift=shift, active=active,
                    roster_revision=roster['revision'] if roster else '',
                    reports=store.search_finalized_shifts(limit=20), clients=store.online_clients(),
                    history=store.officer_history())

    def check(self, request):
        row = self._store().officer_action(request.action_id)
        if row:
            if row['intent'] != request.intent:
                raise BusyError('Το αναγνωριστικό αφορά διαφορετική ενέργεια ή χειριστή.')
            return PositionOutcome('CONFIRMED', row, 'Η ενέργεια επιβεβαιώθηκε κεντρικά.')
        return PositionOutcome('NOT_COMMITTED', message='Δεν βρέθηκε αποδεκτή ενέργεια με αυτό το αναγνωριστικό.')

    def execute(self, request):
        try:
            if not request.confirmed:
                raise ValueError('Απαιτείται ρητή επιβεβαίωση πριν από τη μεταβολή.')
            store = self._store()
            previous = store.officer_action(request.action_id)
            if previous:
                return self.check(request)
            people = {p.agms: p for p in self.people(store)}
            officer = people.get(request.officer_agms)
            if not officer:
                raise ValueError('Το δηλωμένο ΑΓΜΣ ΑΞΥΠ δεν υπάρχει στην κεντρική λίστα.')
            values = request.values
            reason = values.get('reason', '').strip()
            intent = dict(action_id=request.action_id, action=request.action,
                          declared_officer=store._person_payload(officer), identity='DECLARED_NOT_AUTHENTICATED',
                          recorded_at=request.recorded_at, reason=reason, intent=request.intent)
            store.command = intent
            if request.action in ('REMOTE_START', 'REMOTE_END', 'CORRECT_START'):
                if len(reason) < 5:
                    raise ValueError('Συμπληρώστε αιτιολογία τουλάχιστον 5 χαρακτήρων.')
                person = people.get(values['agms'])
                if not person:
                    raise ValueError('Ο αστυνομικός δεν υπάρχει στην κεντρική λίστα.')
                if request.action == 'REMOTE_START':
                    if values['position'] not in {str(i) for i in range(1, 15)}:
                        raise ValueError('Επιλέξτε φυσική θέση 1 έως 14.')
                    store.start(person, values['position'], values['direction'],
                        event_id=request.action_id, when=datetime.fromisoformat(values['when']), sync_shift=False)
                elif request.action == 'REMOTE_END':
                    if not values.get('expected_start_id'):
                        raise ValueError('Απαιτείται το επιβεβαιωμένο αναγνωριστικό ΕΝΑΡΞΗΣ.')
                    store.end(person, expected_start_event_id=values['expected_start_id'],
                        event_id=request.action_id, end_officer=officer, end_reason=reason,
                        when=datetime.fromisoformat(values['when']))
                else:
                    store.correct_declared_start(person.agms, datetime.fromisoformat(values['new_time']),
                        values['expected_start_id'], values['expected_timestamp'], intent)
                if not store.officer_action(request.action_id):
                    raise BusyError('Η ενέργεια δεν μεταβάλλει πλέον την επιλεγμένη καταχώριση. Επανελέγξτε.')
            elif request.action == 'SHIFT_START':
                result = store.start_officer_shift(officer)
                store.finish_document(result)
            elif request.action == 'SHIFT_END':
                result = store.end_officer_shift(officer, expected_shift_id=values['expected_shift_id'])
                store.finish_document(result)
            elif request.action == 'MEMBER_STATE':
                if values['agms'] not in people:
                    raise ValueError('Ο αστυνομικός δεν υπάρχει στην κεντρική λίστα.')
                result = store.set_shift_member_state(values['agms'], values['state'], values['expected_shift_id'])
                store.finish_document(result)
            elif request.action == 'PERSONNEL_IMPORT':
                self._import(store, request, intent)
            elif request.action == 'MESSAGE':
                result = store.send_message({**store._person_payload(officer), 'identity': 'DECLARED'},
                                            values['targets'], values['text'])
                store.finish_document(result)
            else:
                raise ValueError('Μη έγκυρη ενέργεια ΑΞΥΠ.')
            return self.check(request)
        except Exception as error:
            try:
                result = self.check(request)
            except Exception:
                return PositionOutcome('UNKNOWN', message=UNCONFIRMED)
            if result.status == 'CONFIRMED':
                return result
            return PositionOutcome('NOT_COMMITTED', message=str(error))

    def _import(self, store, request, intent):
        store._event_path({'event_id': request.action_id, 'timestamp': request.recorded_at})
        path = store.root / 'personnel_revisions' / (request.action_id + '.xlsx')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != request.workbook:
                raise BusyError('Διαφορετικό αρχείο με ίδιο αναγνωριστικό.')
        else:
            # O_EXCL: even a late writer cannot replace a published workbook.
            import os
            with path.open('xb') as file:
                file.write(request.workbook); file.flush(); os.fsync(file.fileno())
        people = PersonnelRepository.load(path)
        data = dict(path=str(path.relative_to(store.root)), people=len(people),
                    sha256=hashlib.sha256(request.workbook).hexdigest())
        store.publish_document('personnel', data, path, request.values['expected_revision'], intent)

    def report(self, officer_agms, shift_id=''):
        from position_tracking_pdf import create_shift_pdf
        state = self.snapshot(officer_agms)
        store = self._store()
        shift = store.get_shift(shift_id) if shift_id else store.current_report_shift()
        if not shift:
            raise ValueError('Δεν υπάρχει διαθέσιμη αναφορά.')
        return create_shift_pdf(store, shift, {p.agms: p for p in state['people']})

    @staticmethod
    def preview_personnel(path):
        path = Path(path)
        people = PersonnelRepository.load(path)
        return path.read_bytes(), len(people)

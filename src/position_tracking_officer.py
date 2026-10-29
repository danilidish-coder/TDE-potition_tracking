"""Simple central officer commands. AGMS is declared attribution, not identity."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import uuid

from position_tracking_central import CentralOperator, PositionOutcome, UNCONFIRMED
from position_tracking_common import _clean, format_when
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

CLOCK_TOLERANCE = timedelta(minutes=2)
OLD_TIME_LIMIT = timedelta(hours=24)
RECENT_STARTS_WINDOW = timedelta(hours=24)
RECENT_SESSIONS_WINDOW = timedelta(hours=72)


def short_name(item):
    """«Παπαδόπουλος Γ.» από εγγραφή θέσης ή προσωπικού."""
    surname, given = _clean(item.get('surname')), _clean(item.get('given_name'))
    if surname:
        return f'{surname} {given[:1]}.' if given else surname
    return _clean(item.get('full_name')) or _clean(item.get('agms'))


def station_labels(clients, active):
    """Για κάθε ενεργό σταθμό: «ΣΤΑΘΜΟΣ — Όνομα — Θέση Ν» ή «ΣΤΑΘΜΟΣ — (ελεύθερος)».

    Σταθμός = υπολογιστής/χρήστης των ενεργών καρτελών. Ο τελευταίος που έκανε
    ΕΝΑΡΞΗ και δεν έκανε ΛΗΞΗ εμφανίζεται. Οι ΕΝΑΡΞΕΙΣ που έκανε ο ΑΞΥΠ από
    το πάνελ του (απομακρυσμένες) δεν ανήκουν σε σταθμό.
    """
    own = [a for a in active if (a.get('declared_action') or {}).get('action') != 'REMOTE_START']
    computers = [_clean(c.get('computer')).casefold() for c in clients]
    labels = {}
    for client in clients:
        computer = _clean(client.get('computer'))
        user = _clean(client.get('user')).casefold()
        mine = [a for a in own if _clean(a.get('computer')).casefold() == computer.casefold()
                and _clean(a.get('user')).casefold() == user]
        if not mine:
            mine = [a for a in own if _clean(a.get('computer')).casefold() == computer.casefold()
                    and not _clean(a.get('user'))]
        name = computer or _clean(client.get('client_id'))
        if computers.count(computer.casefold()) > 1 and _clean(client.get('user')):
            name += f" ({_clean(client.get('user'))})"
        if mine:
            latest = max(mine, key=lambda a: _clean(a.get('timestamp')))
            labels[client['client_id']] = f"{name} — {short_name(latest)} — Θέση {_clean(latest.get('position'))}"
        else:
            labels[client['client_id']] = f'{name} — (ελεύθερος)'
    return labels


def check_chosen_time(value, reference, minimum=None, confirm_old=False, what='Η ώρα'):
    """Κοινός έλεγχος ώρας που επιλέγει ο ΑΞΥΠ: όχι μέλλον, όχι πάνω από 24 ώρες πίσω χωρίς επιβεβαίωση."""
    if value > reference + CLOCK_TOLERANCE:
        raise ValueError(f'{what} δεν μπορεί να είναι μελλοντική.')
    if minimum is not None and value < minimum:
        raise ValueError(f'{what} δεν μπορεί να προηγείται της {format_when(minimum)}.')
    if reference - value > OLD_TIME_LIMIT and not confirm_old:
        raise ValueError(f'{what} είναι πάνω από 24 ώρες πίσω και χρειάζεται ρητή επιβεβαίωση.')


ACTION_LABELS = {
    'REMOTE_START': 'Απομακρυσμένη ΕΝΑΡΞΗ', 'REMOTE_END': 'Απομακρυσμένη ΛΗΞΗ',
    'CORRECT_START': 'Διόρθωση ώρας ΕΝΑΡΞΗΣ', 'CORRECT_END': 'Διόρθωση ώρας ΛΗΞΗΣ',
    'HISTORICAL_ADD': 'Προσθήκη εργασίας',
    'SHIFT_START': 'ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ', 'SHIFT_END': 'ΛΗΞΗ ΒΑΡΔΙΑΣ', 'SHIFT_TIME_CORRECT': 'Διόρθωση ώρας βάρδιας',
    'MEMBER_STATE': 'Συμμετοχή στη βάρδια', 'PERSONNEL_IMPORT': 'Ενημέρωση προσωπικού', 'MESSAGE': 'Μήνυμα',
}


def describe_history(receipts):
    """Αναγνώσιμο ιστορικό ενεργειών ΑΞΥΠ με ευρωπαϊκές ημερομηνίες (αντί για ωμό JSON)."""
    blocks = []
    for receipt in receipts:
        values = (receipt.get('intent') or {}).get('values') or {}
        action = receipt.get('action', '')
        lines = [f"{format_when(receipt.get('accepted_at'), seconds=True)} — {ACTION_LABELS.get(action, action)}",
                 'ΑΞΥΠ: ' + _clean((receipt.get('declared_officer') or {}).get('full_name'))]
        person = (receipt.get('after') or receipt.get('before') or {})
        if isinstance(person, dict) and person.get('full_name'):
            place = f" — Θέση {person['position']}" if person.get('position') else ''
            lines.append('Άτομο: ' + _clean(person['full_name']) + place)
        for key, label in (('when', 'Ώρα'), ('new_time', 'Νέα ώρα'), ('start_at', 'Από'), ('end_at', 'Έως')):
            if values.get(key):
                lines.append(f"{label}: {format_when(values[key])}")
        if values.get('which') and values.get('shift_id'):
            lines.append('Διορθώθηκε η ώρα ' + ('έναρξης' if values['which'] == 'start_at' else 'λήξης') + ' της βάρδιας')
        if receipt.get('before') and isinstance(receipt['before'], dict) and receipt['before'].get('timestamp'):
            lines.append('Προηγούμενη ώρα: ' + format_when(receipt['before']['timestamp']))
        if _clean(receipt.get('reason')):
            lines.append('Αιτιολογία: ' + _clean(receipt['reason']))
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) if blocks else 'Δεν υπάρχουν καταγεγραμμένες ενέργειες.'


def chosen_time(values, key='when', default=None):
    text = _clean(values.get(key))
    return datetime.fromisoformat(text) if text else default


class CentralOfficer(CentralOperator):
    def _store(self):
        if not self.root.is_dir():
            raise OSError(UNCONFIRMED)
        return OfficerStore(self.root)

    def snapshot(self, officer_agms):
        store = self._store()
        people = self.people(store)
        found = PersonnelRepository.find(people, officer_agms)
        if len(found) > 1:
            raise ValueError('Βρέθηκαν πολλοί με αυτό το όνομα. Γράψτε επώνυμο και όνομα ή το ΑΓΜΣ.')
        officer = found[0] if found else None
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
        clients = store.online_clients()
        since = (datetime.now() - RECENT_STARTS_WINDOW).isoformat(timespec='seconds')
        recent = []
        for row in store._position_rows(
                "SELECT payload FROM position_operations WHERE kind='START' AND state='COMMITTED' "
                "AND json_extract(payload,'$.timestamp')>=? ORDER BY json_extract(payload,'$.timestamp')", (since,)):
            item = json.loads(row['payload'])
            recent.append(dict(agms=_clean(item.get('agms')), full_name=_clean(item.get('full_name')),
                               position=_clean(item.get('position')), timestamp=_clean(item.get('timestamp'))))
        recent_sessions = [dict(agms=_clean(row['agms']), full_name=_clean(row['full_name']),
                                position=_clean(row['position']), direction=_clean(row['direction']),
                                start_event_id=_clean(row['start_event_id']), end_event_id=_clean(row['end_event_id']),
                                start_at=_clean(row['start_at']), end_at=_clean(row['end_at']))
                           for row in store.search_personnel_sessions(date_from=(datetime.now() - RECENT_SESSIONS_WINDOW).date())
                           if not row.get('historical') and _clean(row['end_at'])
                           >= (datetime.now() - RECENT_SESSIONS_WINDOW).isoformat(timespec='seconds')]
        return dict(officer=officer, people=people, shift=shift, active=active, recent_sessions=recent_sessions,
                    roster_revision=roster['revision'] if roster else '',
                    reports=store.search_finalized_shifts(limit=20), clients=clients,
                    station_labels=station_labels(clients, active), recent_starts=recent,
                    server_now=datetime.now().isoformat(timespec='seconds'))

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
                          personnel_revision=store._personnel_revision,
                          recorded_at=request.recorded_at, reason=reason, intent=request.intent)
            store.command = intent
            if request.action in ('REMOTE_START', 'REMOTE_END', 'CORRECT_START'):
                if len(reason) < 5:
                    raise ValueError('Συμπληρώστε αιτιολογία τουλάχιστον 5 χαρακτήρων.')
                person = people.get(values['agms'])
                if not person:
                    raise ValueError('Ο αστυνομικός δεν υπάρχει στην κεντρική λίστα.')
                reference = datetime.fromisoformat(request.recorded_at)
                check_chosen_time(datetime.fromisoformat(values['new_time' if request.action == 'CORRECT_START' else 'when']),
                                  reference, confirm_old=bool(values.get('confirm_old')))
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
            elif request.action == 'CORRECT_END':
                if len(reason) < 5:
                    raise ValueError('Συμπληρώστε αιτιολογία τουλάχιστον 5 χαρακτήρων.')
                person = people.get(values['agms'])
                if not person:
                    raise ValueError('Ο αστυνομικός δεν υπάρχει στην κεντρική λίστα.')
                new_when = datetime.fromisoformat(values['new_time'])
                check_chosen_time(new_when, datetime.fromisoformat(request.recorded_at),
                                  confirm_old=bool(values.get('confirm_old')), what='Η ώρα ΛΗΞΗΣ')
                store.correct_declared_end(person.agms, values['expected_start_id'], values['expected_end_id'],
                                           values['expected_timestamp'], new_when, intent)
                if not store.officer_action(request.action_id):
                    raise BusyError('Η ενέργεια δεν μεταβάλλει πλέον την επιλεγμένη καταχώριση. Επανελέγξτε.')
            elif request.action == 'HISTORICAL_ADD':
                person = people.get(values['agms'])
                if not person:
                    raise ValueError('Ο αστυνομικός δεν υπάρχει στην κεντρική λίστα.')
                store.add_historical_completed(
                    shift_id=values['shift_id'], person=person,
                    position=values['position'], direction=values['direction'],
                    start_at=datetime.fromisoformat(values['start_at']),
                    end_at=datetime.fromisoformat(values['end_at']),
                    reason=reason, intent=intent)
            elif request.action == 'SHIFT_START':
                reference = datetime.fromisoformat(request.recorded_at)
                when = chosen_time(values, default=reference.replace(microsecond=0))
                check_chosen_time(when, reference, confirm_old=bool(values.get('confirm_old')), what='Η ώρα έναρξης βάρδιας')
                result = store.start_officer_shift(officer, when=when)
                store.finish_document(result)
            elif request.action == 'SHIFT_END':
                reference = datetime.fromisoformat(request.recorded_at)
                when = chosen_time(values, default=reference.replace(microsecond=0))
                current = store.current_shift()
                check_chosen_time(when, reference, confirm_old=bool(values.get('confirm_old')), what='Η ώρα λήξης βάρδιας',
                                  minimum=datetime.fromisoformat(current['start_at']) if current else None)
                result = store.end_officer_shift(officer, when=when, expected_shift_id=values['expected_shift_id'])
                store.finish_document(result)
            elif request.action == 'SHIFT_TIME_CORRECT':
                if len(reason) < 5:
                    raise ValueError('Συμπληρώστε αιτιολογία τουλάχιστον 5 χαρακτήρων.')
                result = store.correct_shift_time(
                    values['shift_id'], values['which'], datetime.fromisoformat(values['new_time']),
                    reason, officer, datetime.fromisoformat(request.recorded_at), bool(values.get('confirm_old')))
                if result.get('kind') == 'CURRENT':
                    store.finish_document(result['shift'])
                else:
                    store.publish_shift_correction(result['before'], result['shift'], intent)
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

    def conflicts(self, officer_agms, action, values):
        """Προειδοποιήσεις πριν από ώρα που επιλέγει ο ΑΞΥΠ. Δεν γράφει τίποτα."""
        state = self.snapshot(officer_agms)
        store = self._store()
        now = datetime.now()
        errors, warnings = [], []
        agms = _clean(values.get('agms'))
        position = _clean(values.get('position'))
        start_text = values.get('new_time') if action in ('CORRECT_START', 'CORRECT_END') else values.get('when')
        try:
            moment = datetime.fromisoformat(start_text)
        except (TypeError, ValueError):
            return dict(errors=['Μη έγκυρη ημερομηνία και ώρα.'], warnings=[])
        if moment > now + CLOCK_TOLERANCE:
            errors.append('Η ώρα δεν μπορεί να είναι μελλοντική.')
        elif now - moment > OLD_TIME_LIMIT:
            warnings.append('Η ώρα είναι πάνω από 24 ώρες πίσω.')
        if action == 'CORRECT_END':
            return store.end_correction_check(values, moment, errors, warnings)
        active = next((a for a in state['active'] if a['agms'] == agms), None)
        if action in ('REMOTE_END', 'CORRECT_START') and active and action == 'REMOTE_END':
            if moment < datetime.fromisoformat(active['timestamp']):
                errors.append('Η ώρα ΛΗΞΗΣ προηγείται της ΕΝΑΡΞΗΣ (' + format_when(active['timestamp']) + ').')
        low, high = moment, now
        if action == 'REMOTE_END' and active:
            low, high = datetime.fromisoformat(active['timestamp']), moment
        if action == 'CORRECT_START' and active:
            low, high = moment, datetime.fromisoformat(active['timestamp'])
        if action == 'REMOTE_START' and not errors:
            rows = store.search_personnel_sessions(person_query=agms, date_from=low.date(), date_to=high.date())
            for row in rows:
                if _clean(row.get('agms')) != agms:
                    continue
                if row['start_at'] < high.isoformat(timespec='seconds') and row['end_at'] > low.isoformat(timespec='seconds'):
                    warnings.append(f"Επικάλυψη με άλλη εργασία του ίδιου ατόμου: Θέση {row['position']} "
                                    f"{format_when(row['start_at'])} – {format_when(row['end_at'])}.")
            if position:
                for row in store.search_personnel_sessions(position=position, date_from=low.date(), date_to=high.date()):
                    if _clean(row.get('agms')) == agms:
                        continue
                    if row['start_at'] < high.isoformat(timespec='seconds') and row['end_at'] > low.isoformat(timespec='seconds'):
                        warnings.append(f"Η θέση {position} ήταν κατειλημμένη από {_clean(row.get('full_name'))} "
                                        f"{format_when(row['start_at'])} – {format_when(row['end_at'])}.")
        if action == 'CORRECT_START' and active and not errors:
            for row in store.search_personnel_sessions(person_query=agms, date_from=low.date(), date_to=high.date()):
                if _clean(row.get('agms')) == agms and row['end_at'] > low.isoformat(timespec='seconds') \
                        and row['start_at'] < high.isoformat(timespec='seconds'):
                    warnings.append(f"Η νέα ώρα επικαλύπτεται με προηγούμενη εργασία: Θέση {row['position']} "
                                    f"{format_when(row['start_at'])} – {format_when(row['end_at'])}.")
        return dict(errors=errors, warnings=warnings)

    def shift_correction_preview(self, officer_agms, shift_id, which, new_time):
        """Ποιοι έχουν ΕΝΑΡΞΗ στο νέο διάστημα βάρδιας χωρίς να ανήκουν σε αυτή."""
        state = self.snapshot(officer_agms)
        store = self._store()
        shift = store.get_shift(shift_id) or state['shift']
        if not shift:
            raise ValueError('Δεν βρέθηκε η βάρδια.')
        warnings = []
        moment = datetime.fromisoformat(new_time)
        if moment > datetime.now() + CLOCK_TOLERANCE:
            return dict(errors=['Η ώρα δεν μπορεί να είναι μελλοντική.'], warnings=[])
        if which == 'start_at' and shift.get('end_at') and moment >= datetime.fromisoformat(shift['end_at']):
            return dict(errors=['Η έναρξη πρέπει να προηγείται της λήξης της βάρδιας.'], warnings=[])
        if which == 'end_at' and moment <= datetime.fromisoformat(shift['start_at']):
            return dict(errors=['Η λήξη πρέπει να έπεται της έναρξης της βάρδιας.'], warnings=[])
        known = set(shift.get('approved', [])) | set(shift.get('excluded', [])) | set(shift.get('pending', []))
        low, high = (moment, datetime.fromisoformat(shift.get('end_at') or datetime.now().isoformat(timespec='seconds'))) \
            if which == 'start_at' else (datetime.fromisoformat(shift['start_at']), moment)
        names = set()
        for row in store._position_rows(
                "SELECT payload FROM position_operations WHERE kind='START' AND state='COMMITTED' "
                "AND json_extract(payload,'$.timestamp')>=? AND json_extract(payload,'$.timestamp')<?",
                (low.isoformat(timespec='seconds'), high.isoformat(timespec='seconds'))):
            item = json.loads(row['payload'])
            if _clean(item.get('agms')) not in known:
                names.add(_clean(item.get('full_name')) or _clean(item.get('agms')))
        if names and shift.get('status') == 'FINALIZED':
            warnings.append('Στο νέο διάστημα υπάρχουν ΕΝΑΡΞΕΙΣ ατόμων που δεν ανήκουν στη βάρδια και δεν θα '
                            'προστεθούν αυτόματα: ' + ', '.join(sorted(names)[:8]) + ('…' if len(names) > 8 else ''))
        elif names:
            warnings.append('Θα μπουν σε ΑΝΑΜΟΝΗ για απόφαση: ' + ', '.join(sorted(names)[:8]) + ('…' if len(names) > 8 else ''))
        return dict(errors=[], warnings=warnings)

    def _import(self, store, request, intent):
        store._event_path({'event_id': request.action_id, 'timestamp': request.recorded_at})
        digest = hashlib.sha256(request.workbook).hexdigest()
        path = store.root / 'personnel_revisions' / (digest + '.xlsx')
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != request.workbook:
                raise BusyError('Διαφορετικό αρχείο με ίδιο αναγνωριστικό.')
        else:
            # Publish only complete bytes. Content-addressed paths keep a late
            # different import from overwriting an accepted roster revision.
            import os
            temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
            with temp.open('xb') as file:
                file.write(request.workbook); file.flush(); os.fsync(file.fileno())
            os.replace(temp, path)
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
        return create_shift_pdf(store, shift, {p.agms: p for p in state['people']},
                                target=store.reports / ('REPORT_' + uuid.uuid4().hex + '.pdf'))

    def find_reports(self, officer_agms, day_text):
        self.snapshot(officer_agms)
        from position_tracking_common import parse_day
        chosen = parse_day(day_text)
        return self._store().search_finalized_shifts(
            date_from=chosen, date_to=chosen, limit=100)

    @staticmethod
    def preview_personnel(path):
        path = Path(path)
        data = path.read_bytes()
        people = PersonnelRepository.load(data)
        return data, len(people)

    def personal_report(self, officer_agms, person_agms):
        from position_tracking_pdf import create_personnel_history_pdf
        self.snapshot(officer_agms)
        store = self._store()
        rows = store.search_personnel_sessions(person_query=person_agms)
        return create_personnel_history_pdf(rows, 'ΑΓΜΣ: ' + person_agms,
                    target=store.reports / ('PERSON_' + uuid.uuid4().hex + '.pdf'))

    def history(self, officer_agms):
        self.snapshot(officer_agms)
        return self._store().officer_history()

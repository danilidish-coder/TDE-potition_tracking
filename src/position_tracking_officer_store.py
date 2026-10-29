"""Reuse shift/message engine, staging document writes into one audited SQL commit."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from position_tracking_common import _clean, format_when
from position_tracking_store import SharedEventStore
from position_tracking_store_io import BusyError


class OfficerStore(SharedEventStore):
    def __init__(self, root):
        self.command = None
        self.staged = None
        self.observed_revision = ''
        super().__init__(root)
        self.repair_officer_documents()

    def document(self, key):
        rows = self._position_rows('SELECT * FROM officer_documents WHERE document_key=?', (key,))
        return rows[0] if rows else None

    def current_shift(self):
        if getattr(self, '_officer_ledger_ready', False):
            row = self.document('shift')
            self.observed_revision = row['revision'] if row else ''
            data = self.staged[1] if self.staged and self.staged[0] == 'shift' else json.loads(row['payload']) if row else None
            if data is not None:
                return deepcopy(data) if data['status'] == 'ACTIVE' else None
        return super().current_shift()

    def current_report_shift(self):
        row = self.document('shift')
        return json.loads(row['payload']) if row else super().current_report_shift()

    def _write_event(self, event):
        if self.command:
            event['declared_action'] = self.command
        return super()._write_event(event)

    def _atomic_json(self, path, data):
        if self.command and path == self._current_shift_path():
            self.staged = ('shift', deepcopy(data), path)
        elif self.command and path.parent == self.comm_messages:
            self.staged = ('message:' + data['message_id'], deepcopy(data), path)
        else:
            super()._atomic_json(path, data)

    def _store_shift_snapshot(self, shift, make_current_report=False):
        if not self.command:
            super()._store_shift_snapshot(shift, make_current_report)

    def log_admin_action(self, action, details=None):
        if not self.command:
            return super().log_admin_action(action, details)
        # The authoritative receipt is committed with the mutation below.

    def publish_document(self, key, data, path, expected_revision, intent, result=None):
        with self._shift_db_write_lock(), self._shift_db_connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT payload FROM officer_actions WHERE action_id=?', (intent['action_id'],)).fetchone()
            if old:
                receipt = json.loads(old['payload'])
                if receipt['intent'] != intent['intent']:
                    raise BusyError('Το αναγνωριστικό αφορά άλλη ενέργεια.')
                return receipt
            row = db.execute('SELECT * FROM officer_documents WHERE document_key=?', (key,)).fetchone()
            if (row['revision'] if row else '') != expected_revision:
                raise BusyError('Τα κεντρικά δεδομένα άλλαξαν. Απαιτείται επανέλεγχος.')
            receipt = {**intent, 'record_id': data.get('shift_id') or data.get('message_id') or key,
                       'before': json.loads(row['payload']) if row else None, 'after': data,
                       'result': result if result is not None else data}
            self._insert_officer_action(db, receipt)
            db.execute('INSERT OR REPLACE INTO officer_documents VALUES (?,?,?,?,0)',
                       (key, intent['action_id'], json.dumps(data, ensure_ascii=False), str(path.relative_to(self.root))))
            if key == 'shift':
                self._upsert_shift_con(db, data)
                db.execute("INSERT OR REPLACE INTO meta VALUES ('current_report_shift_id',?)", (data['shift_id'],))
        self.repair_officer_documents()
        return receipt

    def finish_document(self, result):
        if not self.staged:
            raise BusyError('Δεν επιβεβαιώθηκε η μεταβολή εγγράφου.')
        key, data, path = self.staged
        expected = self.observed_revision if key == 'shift' else ''
        return self.publish_document(key, data, path, expected, self.command, result)

    def repair_officer_documents(self):
        rows = self._position_rows('SELECT * FROM officer_documents WHERE mirrored=0 LIMIT 257')
        if len(rows) > 256:
            raise BusyError('Υπέρβαση ορίου ανάκαμψης εγγράφων ΑΞΥΠ.')
        for row in rows:
            if row['document_key'] == 'personnel':
                # Metadata pointer only; the immutable workbook already exists.
                self._position_index_write('UPDATE officer_documents SET mirrored=1 WHERE document_key=? AND revision=?',
                                           (row['document_key'], row['revision']))
                continue
            try:
                super()._atomic_json(self.root / row['event_path'], json.loads(row['payload']))
                self._position_index_write('UPDATE officer_documents SET mirrored=1 WHERE document_key=? AND revision=?',
                                           (row['document_key'], row['revision']))
            except OSError:
                break  # SQL receipt remains canonical; central mirror repair only.

    def correct_shift_time(self, shift_id, which, new_when, reason, officer, reference, confirm_old=False):
        """Διόρθωση ώρας έναρξης/λήξης βάρδιας εκ των υστέρων.

        Αλλάζει μόνο τα όρια της βάρδιας (αναφορά και λίστα προσωπικού). Οι
        πραγματικές θέσεις, ΕΝΑΡΞΕΙΣ και ΛΗΞΕΙΣ δεν αγγίζονται. Κρατά το
        ιστορικό των διορθώσεων μέσα στη βάρδια και στην απόδειξη ΑΞΥΠ.
        """
        if which not in ('start_at', 'end_at'):
            raise ValueError('Μη έγκυρη ώρα βάρδιας.')
        document = self.document('shift')
        current = json.loads(document['payload']) if document else None
        is_current = bool(current) and _clean(current.get('shift_id')) == _clean(shift_id)
        before = current if is_current else self.get_shift(shift_id)
        if not before:
            raise ValueError('Δεν βρέθηκε η βάρδια.')
        if which == 'end_at' and _clean(before.get('status')).upper() != 'FINALIZED':
            raise ValueError('Η βάρδια δεν έχει λήξει ακόμη. Χρησιμοποιήστε ΛΗΞΗ ΒΑΡΔΙΑΣ.')
        if new_when > reference + timedelta(minutes=2):
            raise ValueError('Η ώρα δεν μπορεί να είναι μελλοντική.')
        if reference - new_when > timedelta(hours=24) and not confirm_old and which == 'end_at':
            raise ValueError('Η ώρα είναι πάνω από 24 ώρες πίσω και χρειάζεται ρητή επιβεβαίωση.')
        old_text = _clean(before.get(which))
        start = new_when if which == 'start_at' else datetime.fromisoformat(before['start_at'])
        end_text = _clean(before.get('end_at'))
        end = new_when if which == 'end_at' else (datetime.fromisoformat(end_text) if end_text else None)
        if end is not None and end <= start:
            raise ValueError('Η λήξη της βάρδιας πρέπει να έπεται της έναρξης.')
        if new_when.isoformat(timespec='seconds') == old_text:
            raise ValueError('Η νέα ώρα είναι ίδια με την υπάρχουσα.')
        after = deepcopy(before)
        after[which] = new_when.isoformat(timespec='seconds')
        after.setdefault('time_corrections', []).append(dict(
            which=which, previous=old_text, corrected=after[which], reason=_clean(reason),
            officer_agms=officer.agms, officer=self._person_payload(officer),
            recorded_at=reference.isoformat(timespec='seconds')))
        after['updated_at'] = datetime.now().isoformat(timespec='seconds')
        if which == 'start_at' and _clean(after.get('status')).upper() == 'ACTIVE':
            known = {_clean(x) for key in ('approved', 'excluded', 'pending') for x in after.get(key, [])}
            for row in self._position_rows(
                    "SELECT DISTINCT agms FROM position_operations WHERE kind='START' AND state='COMMITTED' "
                    "AND json_extract(payload,'$.timestamp')>=?", (after['start_at'],)):
                if row['agms'] not in known:
                    after.setdefault('pending', []).append(row['agms']); known.add(row['agms'])
        if is_current:
            self.observed_revision = document['revision']
            self.staged = ('shift', deepcopy(after), self._current_shift_path())
            return dict(kind='CURRENT', shift=after, before=before)
        return dict(kind='ARCHIVED', shift=after, before=before)

    def publish_shift_correction(self, before, after, intent):
        """Διόρθωση παλαιότερης (όχι τρέχουσας) βάρδιας μαζί με την απόδειξη ΑΞΥΠ."""
        with self._shift_db_write_lock(), self._shift_db_connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT payload FROM officer_actions WHERE action_id=?', (intent['action_id'],)).fetchone()
            if old:
                receipt = json.loads(old['payload'])
                if receipt['intent'] != intent['intent']:
                    raise BusyError('Το αναγνωριστικό αφορά άλλη ενέργεια.')
                return receipt
            row = db.execute('SELECT data_json FROM shifts WHERE shift_id=?', (after['shift_id'],)).fetchone()
            if not row or json.loads(row['data_json']) != before:
                raise BusyError('Η βάρδια άλλαξε. Απαιτείται επανέλεγχος.')
            receipt = {**intent, 'record_id': after['shift_id'], 'before': before, 'after': after, 'result': after}
            self._insert_officer_action(db, receipt)
            self._upsert_shift_con(db, after)
        return receipt

    def closed_correction_check(self, which, values, moment, errors, warnings):
        """Έλεγχοι πριν από διόρθωση ώρας ΕΝΑΡΞΗΣ/ΛΗΞΗΣ εργασίας που έχει ήδη κλείσει. Δεν γράφει τίποτα."""
        agms, position = _clean(values.get('agms')), _clean(values.get('position'))
        rows = self._position_rows("SELECT payload FROM position_operations WHERE event_id=? AND state='COMMITTED'",
                                   (_clean(values.get('expected_start_id')),))
        if not rows:
            return dict(errors=['Η καταχώριση δεν βρέθηκε πλέον. Ανανεώστε και ξαναδοκιμάστε.'], warnings=[])
        mine = _clean(values.get('expected_end_id'))
        old = datetime.fromisoformat(values['expected_timestamp'])
        other_end = None
        for row in self.search_personnel_sessions(person_query=agms, date_from=min(old, moment).date(),
                                                  date_to=max(old, moment).date()):
            if _clean(row.get('end_event_id')) == mine:
                other_end = row
        if other_end is None:
            return dict(errors=['Η εργασία δεν βρέθηκε πλέον. Ανανεώστε και ξαναδοκιμάστε.'], warnings=[])
        if which == 'end' and moment <= datetime.fromisoformat(other_end['start_at']):
            errors.append('Η ΛΗΞΗ πρέπει να έπεται της ΕΝΑΡΞΗΣ (' + format_when(other_end['start_at']) + ').')
        if which == 'start' and moment >= datetime.fromisoformat(other_end['end_at']):
            errors.append('Η ΕΝΑΡΞΗ πρέπει να προηγείται της ΛΗΞΗΣ (' + format_when(other_end['end_at']) + ').')
        extends = moment > old if which == 'end' else moment < old
        if errors or not extends:
            return dict(errors=errors, warnings=warnings)
        low, high = sorted((old.isoformat(timespec='seconds'), moment.isoformat(timespec='seconds')))
        for other in self.search_personnel_sessions(date_from=min(old, moment).date(), date_to=max(old, moment).date()):
            if _clean(other.get('end_event_id')) == mine or not (other['start_at'] < high and other['end_at'] > low):
                continue
            if _clean(other.get('agms')) == agms:
                warnings.append(f"Επικάλυψη με άλλη εργασία του ίδιου ατόμου: Θέση {other['position']} "
                                f"{format_when(other['start_at'])} – {format_when(other['end_at'])}.")
            elif position and _clean(other.get('position')) == position:
                warnings.append(f"Η θέση {position} είναι κατειλημμένη από {_clean(other.get('full_name'))} "
                                f"{format_when(other['start_at'])} – {format_when(other['end_at'])}.")
        return dict(errors=errors, warnings=warnings)

    def person_closed_sessions(self, agms, limit=150):
        """Όλες οι ολοκληρωμένες εργασίες ενός ατόμου (νεότερες πρώτα), χωρίς ιστορικές καταχωρίσεις."""
        rows = [row for row in self.search_personnel_sessions(person_query=agms)
                if _clean(row.get('agms')) == _clean(agms) and not row.get('historical') and _clean(row.get('end_at'))]
        return rows[:limit]

    def overlap_lines(self, days=30):
        """Κείμενο με όλες τις επικαλύψεις (ίδιο άτομο ή ίδια θέση) των τελευταίων ημερών."""
        since = (datetime.now() - timedelta(days=days)).date()
        items = [dict(row) for row in self.search_personnel_sessions(date_from=since) if _clean(row.get('end_at'))]
        now = datetime.now().isoformat(timespec='seconds')
        for active in self.active_all():
            items.append(dict(agms=_clean(active.get('agms')), full_name=_clean(active.get('full_name')),
                              position=_clean(active.get('position')), direction=_clean(active.get('direction')),
                              start_at=_clean(active.get('timestamp')), end_at=now, open=True))
        items.sort(key=lambda row: row['start_at'])
        found = []
        for index, first in enumerate(items):
            for second in items[index + 1:]:
                if second['start_at'] >= first['end_at']:
                    continue
                same_person = _clean(first['agms']) == _clean(second['agms'])
                if not same_person and _clean(first['position']) != _clean(second['position']):
                    continue
                low, high = second['start_at'], min(first['end_at'], second['end_at'])
                if low >= high:
                    continue
                label = (f"ΙΔΙΟ ΑΤΟΜΟ — {_clean(first['full_name'])} (ΑΓΜΣ {first['agms']})" if same_person
                         else f"ΙΔΙΑ ΘΕΣΗ {first['position']}")

                def line(row):
                    end = 'ΑΝΟΙΚΤΗ' if row.get('open') else format_when(row['end_at'])
                    who = '' if same_person else _clean(row['full_name']) + ': '
                    return f"    {who}Θέση {row['position']} {row['direction']}  {format_when(row['start_at'])} – {end}"
                found.append((low, label + '\n' + line(first) + '\n' + line(second) +
                              f"\n    Επικάλυψη: {format_when(low)} – {format_when(high)}"))
        if not found:
            return f'Δεν βρέθηκαν επικαλύψεις τις τελευταίες {days} ημέρες.'
        found.sort(key=lambda item: item[0])
        return (f'Βρέθηκαν {len(found)} επικαλύψεις (τελευταίες {days} ημέρες).\n'
                'Αν μια ΛΗΞΗ ή ΕΝΑΡΞΗ έγινε αργά, διορθώστε την με «ΔΙΟΡΘΩΣΗ ΟΛΟΚΛΗΡΩΜΕΝΗΣ ΕΡΓΑΣΙΑΣ».\n\n'
                + '\n\n'.join(text for _, text in found))

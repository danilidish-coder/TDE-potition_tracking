"""Central append-only declared-actor receipts; no authentication claim."""
from datetime import datetime, timedelta
import json
from position_tracking_common import _clean, format_when
from position_tracking_store_io import BusyError


class OfficerLedgerMixin:
    def _init_officer_ledger(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS officer_actions (action_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS officer_documents
            (document_key TEXT PRIMARY KEY, revision TEXT NOT NULL, payload TEXT NOT NULL,
             event_path TEXT NOT NULL, mirrored INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS officer_start_heads
            (start_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, timestamp TEXT NOT NULL)''')
        db.execute('''CREATE TABLE IF NOT EXISTS officer_end_heads
            (end_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, timestamp TEXT NOT NULL)''')
        for verb in ('UPDATE', 'DELETE'):
            db.execute(f'''CREATE TRIGGER IF NOT EXISTS officer_actions_no_{verb.lower()}
                BEFORE {verb} ON officer_actions BEGIN SELECT RAISE(ABORT,'immutable officer action'); END''')

    def officer_action(self, action_id):
        rows = self._position_rows('SELECT payload FROM officer_actions WHERE action_id=?', (action_id,))
        return json.loads(rows[0]['payload']) if rows else None

    def officer_history(self):
        return [json.loads(row['payload']) for row in self._position_rows('SELECT payload FROM officer_actions ORDER BY rowid')]

    @staticmethod
    def _insert_officer_action(db, receipt):
        receipt['accepted_at'] = datetime.now().isoformat(timespec='microseconds')
        db.execute('INSERT INTO officer_actions VALUES (?,?)',
                   (receipt['action_id'], json.dumps(receipt, ensure_ascii=False)))

    def _record_position_officer_action(self, db, event):
        intent = event.get('declared_action')
        if not intent:
            return
        before = None
        if event['kind'] == 'END':
            row = db.execute('SELECT payload FROM position_operations WHERE event_id=?',
                             (event['start_event_id'],)).fetchone()
            before = json.loads(row['payload'])
            head = db.execute('SELECT timestamp FROM officer_start_heads WHERE start_id=?',
                              (event['start_event_id'],)).fetchone()
            before['timestamp'] = head['timestamp'] if head else self._effective_start_timestamp(
                before['event_id'], before['timestamp'])
        receipt = {**intent, 'record_id': event.get('start_event_id', event['event_id']),
                   'before': before, 'after': event if event['kind'] == 'START' else None, 'result': event}
        self._insert_officer_action(db, receipt)

    def correct_declared_start(self, agms, new_when, expected_start_id, expected_timestamp, intent):
        if len(intent['reason'].strip()) < 5 or new_when > datetime.now():
            raise ValueError('Απαιτείται αιτιολογία και μη μελλοντική ώρα.')
        with self._position_transaction(agms):
            old = self.officer_action(intent['action_id'])
            if old:
                if old['intent'] != intent['intent']:
                    raise BusyError('Το αναγνωριστικό αφορά άλλη ενέργεια.')
                return old
            with self._shift_db_write_lock(), self._shift_db_connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('''SELECT o.payload FROM position_live l JOIN position_operations o
                    ON o.event_id=l.start_id WHERE l.agms=? AND l.start_id=?''', (agms, expected_start_id)).fetchone()
                if not row:
                    raise BusyError('Η ενεργή θέση άλλαξε. Απαιτείται επανέλεγχος.')
                before = self._apply_start_correction(json.loads(row['payload']))
                if before['timestamp'] != expected_timestamp:
                    raise BusyError('Η ώρα έχει ήδη διορθωθεί. Απαιτείται επανέλεγχος.')
                if new_when.date() != datetime.fromisoformat(before['timestamp']).date():
                    raise ValueError('Η διόρθωση περιορίζεται στην ίδια ημερομηνία.')
                after = {**before, 'timestamp': new_when.isoformat(timespec='seconds')}
                receipt = {**intent, 'record_id': expected_start_id, 'before': before, 'after': after, 'result': after}
                self._insert_officer_action(db, receipt)
                db.execute('INSERT OR REPLACE INTO officer_start_heads VALUES (?,?,?)',
                           (expected_start_id, intent['action_id'], after['timestamp']))
                return receipt

    def correct_declared_end(self, agms, expected_start_id, expected_end_id, expected_timestamp, new_when, intent):
        return self.correct_declared_closed('end', agms, expected_start_id, expected_end_id, expected_timestamp,
                                            new_when, intent)

    def correct_declared_closed(self, which, agms, expected_start_id, expected_end_id, expected_timestamp,
                                new_when, intent):
        """Διόρθωση της ώρας ΕΝΑΡΞΗΣ ('start') ή ΛΗΞΗΣ ('end') εργασίας που έχει ήδη κλείσει.

        Τα αρχικά γεγονότα μένουν αναλλοίωτα. Η νέα ώρα καταχωρείται ως «κεφαλή»
        μαζί με την απόδειξη του ΑΞΥΠ και εφαρμόζεται σε αναφορές, ιστορικό και
        ελέγχους επικάλυψης. Επικάλυψη με άλλες εργασίες δεν εμποδίζει τη διόρθωση
        (ο ΑΞΥΠ ειδοποιείται πριν και μπορεί να τη λύσει διορθώνοντας και την άλλη εργασία).
        """
        if which not in ('start', 'end'):
            raise ValueError('Μη έγκυρη ώρα εργασίας.')
        name = 'ΕΝΑΡΞΗΣ' if which == 'start' else 'ΛΗΞΗΣ'
        if len(intent['reason'].strip()) < 5:
            raise ValueError('Απαιτείται αιτιολογία τουλάχιστον 5 χαρακτήρων.')
        if new_when > datetime.now() + timedelta(minutes=2):
            raise ValueError(f'Η ώρα {name} δεν μπορεί να είναι μελλοντική.')
        with self._position_transaction(agms):
            old = self.officer_action(intent['action_id'])
            if old:
                if old['intent'] != intent['intent']:
                    raise BusyError('Το αναγνωριστικό αφορά άλλη ενέργεια.')
                return old
            with self._shift_db_write_lock(), self._shift_db_connect() as db:
                db.execute('BEGIN IMMEDIATE')
                end_row = db.execute('''SELECT payload FROM position_operations
                    WHERE event_id=? AND kind='END' AND start_id=? AND state='COMMITTED' ''',
                    (expected_end_id, expected_start_id)).fetchone()
                start_row = db.execute('''SELECT payload FROM position_operations
                    WHERE event_id=? AND kind='START' AND state='COMMITTED' ''', (expected_start_id,)).fetchone()
                if not end_row or not start_row:
                    raise BusyError('Η καταχώριση άλλαξε ή δεν υπάρχει πλέον. Απαιτείται επανέλεγχος.')
                raw_end, raw_start = json.loads(end_row['payload']), json.loads(start_row['payload'])
                head = db.execute('SELECT timestamp FROM officer_end_heads WHERE end_id=?', (expected_end_id,)).fetchone()
                end = {**raw_end, 'timestamp': head['timestamp'] if head else raw_end['timestamp']}
                head = db.execute('SELECT timestamp FROM officer_start_heads WHERE start_id=?', (expected_start_id,)).fetchone()
                start = {**raw_start, 'timestamp': head['timestamp'] if head else self._apply_start_correction(raw_start)['timestamp']}
                before = start if which == 'start' else end
                if before['timestamp'] != expected_timestamp:
                    raise BusyError(f'Η ώρα {name} έχει ήδη διορθωθεί. Απαιτείται επανέλεγχος.')
                if _clean(before.get('agms')) != _clean(agms):
                    raise BusyError('Η εργασία ανήκει σε άλλον αστυνομικό.')
                start_at, end_at = datetime.fromisoformat(start['timestamp']), datetime.fromisoformat(end['timestamp'])
                if which == 'start' and new_when >= end_at:
                    raise ValueError('Η ΕΝΑΡΞΗ πρέπει να προηγείται της ΛΗΞΗΣ (' + format_when(end_at) + ').')
                if which == 'end' and new_when <= start_at:
                    raise ValueError('Η ΛΗΞΗ πρέπει να έπεται της ΕΝΑΡΞΗΣ (' + format_when(start_at) + ').')
                stamp = new_when.isoformat(timespec='seconds')
                if stamp == before['timestamp']:
                    raise ValueError('Η νέα ώρα είναι ίδια με την υπάρχουσα.')
                after = {**before, 'timestamp': stamp}
                receipt = {**intent, 'record_id': before.get('event_id', expected_end_id), 'before': before,
                           'after': after, 'result': after}
                self._insert_officer_action(db, receipt)
                if which == 'start':
                    db.execute('INSERT OR REPLACE INTO officer_start_heads VALUES (?,?,?)',
                               (expected_start_id, intent['action_id'], stamp))
                    seconds = max(0, int((end_at - new_when).total_seconds()))
                    db.execute('UPDATE personnel_sessions SET start_at=?, duration_seconds=? WHERE start_event_id=?',
                               (stamp, seconds, expected_start_id))
                else:
                    db.execute('INSERT OR REPLACE INTO officer_end_heads VALUES (?,?,?)',
                               (expected_end_id, intent['action_id'], stamp))
                    seconds = max(0, int((new_when - start_at).total_seconds()))
                    db.execute('UPDATE personnel_sessions SET end_at=?, duration_seconds=? WHERE end_event_id=?',
                               (stamp, seconds, expected_end_id))
                return receipt

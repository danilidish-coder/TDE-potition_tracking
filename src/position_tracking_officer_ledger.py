"""Central append-only declared-actor receipts; no authentication claim."""
from datetime import datetime
import json
from position_tracking_store_io import BusyError


class OfficerLedgerMixin:
    def _init_officer_ledger(self, db):
        db.execute('CREATE TABLE IF NOT EXISTS officer_actions (action_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        db.execute('''CREATE TABLE IF NOT EXISTS officer_documents
            (document_key TEXT PRIMARY KEY, revision TEXT NOT NULL, payload TEXT NOT NULL,
             event_path TEXT NOT NULL, mirrored INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS officer_start_heads
            (start_id TEXT PRIMARY KEY, action_id TEXT NOT NULL, timestamp TEXT NOT NULL)''')
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

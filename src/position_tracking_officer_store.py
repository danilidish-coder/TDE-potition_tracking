"""Reuse shift/message engine, staging document writes into one audited SQL commit."""
from copy import deepcopy
import json
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

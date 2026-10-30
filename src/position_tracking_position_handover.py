"""Atomic confirmed booth handover; immutable central receipt precedes mirrors."""
from datetime import datetime
import json
import os
import socket
import uuid

from position_tracking_common import _clean
from position_tracking_store_io import BusyError


class PositionHandoverMixin:
    def _init_handovers(self, db):
        columns = {row['name'] for row in db.execute('PRAGMA table_info(position_operations)')}
        if 'handover_id' not in columns:
            db.execute("ALTER TABLE position_operations ADD COLUMN handover_id TEXT NOT NULL DEFAULT ''")
        db.execute("""CREATE TABLE IF NOT EXISTS position_handovers (
            handover_id TEXT PRIMARY KEY, receipt TEXT NOT NULL,
            mirrored INTEGER NOT NULL DEFAULT 0)""")

    def handover_receipt(self, operation_id):
        rows = self._position_rows('SELECT receipt FROM position_handovers WHERE handover_id=?', (operation_id,))
        return json.loads(rows[0]['receipt']) if rows else None

    def _handover_evidence(self, row):
        receipt = self.handover_receipt(row['handover_id'])
        event = json.loads(row['payload'])
        if not receipt or event not in (receipt['start'], receipt['end']):
            raise BusyError('Ασυμφωνία κεντρικής απόδειξης αντικατάστασης.')
        return event

    def _handover_events(self):
        if not getattr(self, '_handover_ready', False):
            return []  # Initial legacy shift-index import precedes this schema.
        if not self._position_rows("SELECT value FROM meta WHERE key='position_events_index_v1'"):
            return []  # Failed legacy import: retain its raw diagnostic evidence.
        return [self._apply_start_correction(json.loads(row['payload'])) for row in self._position_rows(
            "SELECT payload FROM position_operations WHERE handover_id<>'' AND state='COMMITTED'")]

    def _mirror_handover(self, receipt):
        # Only immutable per-event paths; never overwrite/delete an AGMS's
        # mutable active marker after another worker may have taken its place.
        for key in ('end', 'start'):
            event = receipt[key]
            self._atomic_json(self._event_path(event), event)
        self._position_index_write('UPDATE position_handovers SET mirrored=1 WHERE handover_id=?',
                                   (receipt['handover_id'],))

    def _recover_handovers(self):
        rows = self._position_rows('SELECT receipt FROM position_handovers WHERE mirrored=0 LIMIT ?',
                                   (self.POSITION_RECOVERY_LIMIT + 1,))
        if len(rows) > self.POSITION_RECOVERY_LIMIT:
            raise BusyError('Υπέρβαση ορίου ανάκαμψης αντικαταστάσεων.')
        for row in rows:
            try:
                self._mirror_handover(json.loads(row['receipt']))
            except OSError:
                # A projection outage cannot undo the fully accepted SQL
                # transaction. Live state, report events and history use receipt.
                break

    def handover(self, person, position, direction, expected_start_id, operation_id,
                 when=None, reason='OPERATOR_CONFIRMED_HANDOVER'):
        """Only call after YES for this exact centrally observed START ID."""
        position, direction = _clean(position), _clean(direction).upper()
        if position not in {str(i) for i in range(1, 15)} or direction not in {'ΕΙΣΟΔΟΣ', 'ΕΞΟΔΟΣ'}:
            raise ValueError('Μη έγκυρη θέση ή κατεύθυνση.')
        if not expected_start_id or not _clean(reason):
            raise ValueError('Απαιτείται επιβεβαιωμένη ΕΝΑΡΞΗ και αιτία αντικατάστασης.')
        actor = {'computer': socket.gethostname(),
                 'windows_user': os.environ.get('USERNAME') or os.environ.get('USER') or '',
                 'agms': person.agms}
        timestamp = (when or datetime.now()).isoformat(timespec='seconds')
        with self._position_transaction(person.agms):
            receipt = self._commit_handover(person, position, direction, expected_start_id,
                                             operation_id, timestamp, actor, _clean(reason))
        try:
            self._mirror_handover(receipt)
        except OSError:
            pass  # Immutable SQL receipt is sufficient confirmation/recovery.
        return receipt['start']

    def _commit_handover(self, person, position, direction, expected_start_id,
                         operation_id, timestamp, actor, reason):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as db:
                db.execute('BEGIN IMMEDIATE')
                previous = db.execute('SELECT receipt FROM position_handovers WHERE handover_id=?',
                                      (operation_id,)).fetchone()
                if previous:
                    receipt = json.loads(previous['receipt'])
                    event = receipt['start']
                    if (event['agms'], event['position'], event['direction'], receipt['previous_start_id']) != (
                            person.agms, position, direction, expected_start_id):
                        raise BusyError('Το αναγνωριστικό αφορά διαφορετική αντικατάσταση.')
                    return receipt  # Never reapply a previously accepted claim.
                claim = db.execute('SELECT * FROM position_live WHERE position=?', (position,)).fetchone()
                if not claim or claim['start_id'] != expected_start_id:
                    raise ValueError('Η θέση άλλαξε. Ελέγξτε ξανά πριν από αντικατάσταση.')
                if db.execute('SELECT 1 FROM position_live WHERE agms=?', (person.agms,)).fetchone():
                    raise ValueError('Ο νέος αστυνομικός έχει ήδη ενεργή θέση. Απαιτείται πρώτα ΛΗΞΗ.')
                old = db.execute("SELECT payload FROM position_operations WHERE event_id=? AND state='COMMITTED'",
                                 (expected_start_id,)).fetchone()
                if not old:
                    raise BusyError('Δεν επιβεβαιώθηκε η προηγούμενη ΕΝΑΡΞΗ.')
                old = self._apply_start_correction(json.loads(old['payload']))
                if old['agms'] != claim['agms'] or old['position'] != position:
                    raise BusyError('Ασυμφωνία κεντρικής κατοχής και αρχικής καταχώρισης.')
                if datetime.fromisoformat(timestamp) < datetime.fromisoformat(old['timestamp']):
                    raise ValueError('Η αντικατάσταση προηγείται της αρχικής ΕΝΑΡΞΗΣ.')
                audit = {'handover_id': operation_id, 'previous_start_id': expected_start_id,
                         'previous_agms': old['agms'], 'next_agms': person.agms,
                         'actor': actor, 'reason': reason}
                end = {key: old[key] for key in ('agms', 'rank', 'surname', 'given_name', 'full_name', 'position', 'direction')}
                end.update(version=2, event_id=uuid.uuid5(uuid.NAMESPACE_OID, 'handover-end:' + operation_id).hex,
                           kind='END', start_event_id=expected_start_id, timestamp=timestamp,
                           computer=actor['computer'], user=actor['windows_user'],
                           end_reason=reason, handover=audit)
                start = dict(version=2, event_id=operation_id, kind='START', timestamp=timestamp,
                             agms=person.agms, rank=person.rank, surname=person.surname,
                             given_name=person.given_name, full_name=person.full_name,
                             position=position, direction=direction, computer=actor['computer'],
                             user=actor['windows_user'], client_id='', handover=audit)
                receipt = dict(handover_id=operation_id, previous_start_id=expected_start_id,
                               recorded_at=datetime.now().isoformat(timespec='seconds'),
                               actor=actor, reason=reason, start=start, end=end)
                for event in (end, start):
                    path = self._event_path(event)  # Validates both immutable IDs.
                    db.execute("""INSERT INTO position_operations
                        (event_id,kind,agms,start_id,event_path,payload,state,settled,attempt,handover_id)
                        VALUES (?,?,?,?,?,?,'COMMITTED',1,?,?)""",
                               (event['event_id'], event['kind'], event['agms'], event.get('start_event_id'),
                                str(path.relative_to(self.root)), json.dumps(event, ensure_ascii=False),
                                operation_id, operation_id))
                db.execute('DELETE FROM position_live WHERE start_id=?', (expected_start_id,))
                db.execute('INSERT INTO position_live VALUES (?,?,?)', (person.agms, position, operation_id))
                self._upsert_personnel_session_con(db, old, end)
                db.execute('INSERT INTO position_handovers (handover_id,receipt) VALUES (?,?)',
                           (operation_id, json.dumps(receipt, ensure_ascii=False)))
                return receipt

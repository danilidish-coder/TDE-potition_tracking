"""D2 security gate: caller-supplied AGMS/Windows labels are not authorization.

These MUST deny until a trusted officer authority exists. Do not mark failures
expected or replace them with an injected allow-all identity. Every write below
uses synthetic personnel and a disposable directory; no GUI or service share.
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore


class OfficerAuthorization(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-d2-untrusted-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.store = SharedEventStore(self.temp.name)
        self.worker = PersonnelRecord('999001', 'TEST', 'WORKER', 'SYNTHETIC')
        self.officer = PersonnelRecord('999099', 'TEST', 'OFFICER', 'SYNTHETIC')
        self.impostor = PersonnelRecord('999098', 'TEST', 'IMPOSTOR', 'SYNTHETIC')
        self.start = self.store.start(self.worker, '1', 'ΕΙΣΟΔΟΣ', event_id='synthetic-start')

    def snapshot(self):
        return {
            'positions': self.store._position_rows('SELECT * FROM position_live'),
            'operations': self.store._position_rows('SELECT * FROM position_operations'),
            'sessions': self.store._position_rows('SELECT * FROM personnel_sessions'),
            'current_shift': self.store._current_shift_path().read_bytes()
                if self.store._current_shift_path().is_file() else None,
            'messages': {str(p.relative_to(self.store.root)): p.read_bytes()
                         for p in self.store.comm_messages.glob('*.json')},
            'audit': (self.store.audit / 'admin_audit.jsonl').read_bytes()
                if (self.store.audit / 'admin_audit.jsonl').is_file() else None,
        }

    def require_denied_without_mutation(self, action, invoke):
        before = self.snapshot()
        try:
            result = invoke()
        except PermissionError:
            self.assertEqual(self.snapshot(), before, 'Denied request still mutated central data')
        else:
            after = self.snapshot()
            evidence = {
                'action': action, 'returned': result.get('status') or result.get('kind') or 'accepted',
                'changed': [key for key in before if before[key] != after[key]],
                'live_before': before['positions'], 'live_after': after['positions'],
                'committed_ENDs': len([row for row in after['operations']
                                      if row['kind'] == 'END' and row['state'] == 'COMMITTED']),
            }
            self.fail('UNAUTHORIZED_OFFICER_ACTION_ACCEPTED: ' + json.dumps(evidence, ensure_ascii=False))

    def test_typed_officer_and_forged_windows_label_cannot_start_shift(self):
        with patch.dict(os.environ, {'USERNAME': 'FAKE_OFFICER', 'USER': 'FAKE_OFFICER'}):
            self.require_denied_without_mutation('SHIFT_START',
                lambda: self.store.start_officer_shift(self.impostor))

    def test_direct_business_call_cannot_bypass_membership_authorization(self):
        self.store.start_officer_shift(self.officer)
        self.require_denied_without_mutation('MEMBER_EXCLUDE',
            lambda: self.store.set_shift_member_state(self.worker.agms, 'EXCLUDED'))

    def test_valid_start_and_shift_ids_do_not_authorize_remote_end(self):
        shift = self.store.start_officer_shift(self.officer)
        self.require_denied_without_mutation('REMOTE_END',
            lambda: self.store.end_officer_shift_member(self.impostor, self.worker.agms,
                shift['shift_id'], self.start['event_id']))

    def test_gui_bypass_cannot_finalize_another_officers_shift(self):
        shift = self.store.start_officer_shift(self.officer)
        self.require_denied_without_mutation('SHIFT_FINALIZE',
            lambda: self.store.end_officer_shift(self.impostor, expected_shift_id=shift['shift_id']))

    def test_caller_supplied_sender_does_not_authorize_official_message(self):
        self.require_denied_without_mutation('OFFICIAL_MESSAGE',
            lambda: self.store.send_message(
                {'agms': self.impostor.agms, 'role': 'OFFICER', 'authorized': True},
                ['SYNTHETIC_CLIENT'], 'SYNTHETIC AUTHORIZATION CHECK'))


if __name__ == '__main__':
    unittest.main()

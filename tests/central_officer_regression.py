"""D2 declared attribution, atomic audit, recovery, roster CAS and physical safety."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_central import CentralOperator
from position_tracking_officer import CentralOfficer, OfficerRequest
from position_tracking_officer_store import OfficerStore
from position_tracking_store import SharedEventStore


def workbook(surname='TARGET'):
    book = Workbook(); sheet = book.active
    sheet.append(['ΑΓΜΣ', 'ΒΑΘΜΟΣ', 'ΕΠΩΝΥΜΟ', 'ΟΝΟΜΑ'])
    for agms, name in [('999001', 'OFFICER'), ('999002', surname), ('999003', 'THIRD')]:
        sheet.append([agms, 'TEST', name, 'SYNTHETIC'])
    out = BytesIO(); book.save(out); book.close()
    return out.getvalue()


class OfficerContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-officer-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / '.tde_runtime'; self.root.mkdir()
        self.original_workbook = workbook()
        self.personnel = self.root / 'personnel.xlsx'; self.personnel.write_bytes(self.original_workbook)
        self.endpoint = CentralOfficer(self.root, self.personnel)
        self.base = (datetime.now() - timedelta(minutes=20)).replace(microsecond=0)

    def command(self, action, **values):
        return OfficerRequest(action, '999001', json.dumps(values), True)

    def start(self, **changes):
        values = dict(agms='999002', position='1', direction='ΕΙΣΟΔΟΣ', when=self.base.isoformat(), reason='Explicit officer action')
        values.update(changes)
        request = self.command('REMOTE_START', **values)
        result = self.endpoint.execute(request)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        return request, result.event['result']

    def store(self):
        return OfficerStore(self.root)

    def test_known_declared_officer_and_confirmation_required_before_writes(self):
        request = self.command('SHIFT_START')
        for bad in (replace(request, confirmed=False), replace(request, officer_agms='UNKNOWN')):
            self.assertEqual(self.endpoint.execute(bad).status, 'NOT_COMMITTED')
        self.assertIsNone(self.store().current_shift())
        self.assertEqual(self.store().officer_history(), [])

    def test_remote_start_audit_and_end_idempotency_preserve_newer_start(self):
        request, event = self.start()
        receipt = self.store().officer_action(request.action_id)
        self.assertEqual(receipt['declared_officer']['agms'], '999001')
        self.assertIn('OFFICER', receipt['declared_officer']['full_name'])
        self.assertEqual(receipt['identity'], 'DECLARED_NOT_AUTHENTICATED')
        self.assertIsNone(receipt['before']); self.assertEqual(receipt['after']['event_id'], event['event_id'])
        end = self.command('REMOTE_END', agms='999002', expected_start_id=event['event_id'],
                           when=(self.base + timedelta(minutes=1)).isoformat(), reason='Explicit remote END')
        result = self.endpoint.execute(end)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        self.assertEqual(result.event['record_id'], event['event_id'])
        self.assertIsNone(result.event['after']); self.assertEqual(result.event['before']['event_id'], event['event_id'])
        newer, _ = self.start(when=(self.base + timedelta(minutes=2)).isoformat())
        self.assertEqual(self.endpoint.execute(end).event, result.event)
        self.assertEqual(self.store().get_active('999002')['event_id'], newer.action_id)
        self.assertEqual(len(self.store().officer_history()), 3)

    def test_correction_chain_is_append_only_and_raw_start_remains_immutable(self):
        request, event = self.start()
        raw = {str(p): p.read_bytes() for p in self.store().events.rglob('*.json')}
        first = self.command('CORRECT_START', agms='999002', expected_start_id=event['event_id'],
            expected_timestamp=event['timestamp'], new_time=(self.base - timedelta(minutes=1)).isoformat(), reason='First correction reason')
        result = self.endpoint.execute(first)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        values = first.values; values.update(expected_timestamp=result.event['after']['timestamp'],
            new_time=(self.base - timedelta(minutes=2)).isoformat(), reason='Second correction reason')
        second = self.command('CORRECT_START', **values)
        self.assertEqual(self.endpoint.execute(second).status, 'CONFIRMED')
        self.assertEqual(self.endpoint.execute(first).event, result.event)
        self.assertEqual(self.store().officer_action(second.action_id)['before']['timestamp'], values['expected_timestamp'])
        self.assertEqual({str(p): p.read_bytes() for p in self.store().events.rglob('*.json')}, raw)
        with self.store()._shift_db_connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM officer_actions')
        self.assertEqual(len(self.store().officer_history()), 3)
        self.assertEqual(self.store().get_active('999002')['timestamp'], values['new_time'])

    def test_concurrent_corrections_require_exact_previous_value(self):
        _, event = self.start()
        def correct(i):
            return self.endpoint.execute(self.command('CORRECT_START', agms='999002',
                expected_start_id=event['event_id'], expected_timestamp=event['timestamp'],
                new_time=(self.base - timedelta(seconds=i+1)).isoformat(), reason='Concurrent correction'))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(correct, range(6)))
        self.assertEqual(sum(r.status == 'CONFIRMED' for r in results), 1)
        self.assertEqual(len(self.store().officer_history()), 2)

    def test_concurrent_remote_starts_have_one_central_winner(self):
        def claim(i):
            request = self.command('REMOTE_START', agms='999002' if i%2 else '999003',
                position='1', direction='ΕΙΣΟΔΟΣ', when=self.base.isoformat(), reason='Concurrent officer START')
            return self.endpoint.execute(request)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(claim, range(6)))
        self.assertEqual(sum(r.status == 'CONFIRMED' for r in results), 1)
        self.assertEqual(len(self.store().active_all()), 1)
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_lost_start_commit_ack_recovers_same_action_and_history(self):
        original = OfficerStore._commit_position_attempt
        dropped = []
        def lost_ack(store, *args):
            result = original(store, *args)
            if not dropped:
                dropped.append(True)
                raise OSError('synthetic lost commit ACK')
            return result
        with patch.object(OfficerStore, '_commit_position_attempt', lost_ack):
            request, _ = self.start()
        self.assertEqual(self.endpoint.execute(request).status, 'CONFIRMED')
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_audit_failure_rolls_back_position_acceptance_and_recovers(self):
        store = self.store()
        with store._shift_db_connect() as db:
            db.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON officer_actions BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        request = self.command('REMOTE_START', agms='999002', position='1', direction='ΕΙΣΟΔΟΣ',
                               when=self.base.isoformat(), reason='Audit fault boundary')
        self.assertEqual(self.endpoint.execute(request).status, 'UNKNOWN')
        self.assertEqual(store._position_rows('SELECT * FROM position_live'), [])
        self.assertEqual(store.officer_history(), [])
        with store._shift_db_connect() as db:
            db.execute('DROP TRIGGER fail_audit')
        self.assertEqual(self.endpoint.check(request).status, 'CONFIRMED')
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_shift_membership_and_next_shift_preserve_open_physical_position(self):
        _, event = self.start()
        shift = self.endpoint.execute(self.command('SHIFT_START'))
        self.assertEqual(shift.status, 'CONFIRMED', shift.message)
        shift_id = shift.event['result']['shift_id']
        for state in ('EXCLUDED', 'APPROVED'):
            result = self.endpoint.execute(self.command('MEMBER_STATE', agms='999002', state=state, expected_shift_id=shift_id))
            self.assertEqual(result.status, 'CONFIRMED', result.message)
        final = self.endpoint.execute(self.command('SHIFT_END', expected_shift_id=shift_id))
        self.assertEqual(final.status, 'CONFIRMED', final.message)
        self.assertEqual(self.endpoint.execute(self.command('SHIFT_START')).status, 'CONFIRMED')
        self.assertEqual(self.store().get_active('999002')['event_id'], event['event_id'])
        self.assertFalse([e for e in self.store().iter_all_events() if e['kind'] == 'END'])

    def test_roster_published_once_and_visible_without_station_cache(self):
        request = replace(self.command('PERSONNEL_IMPORT', expected_revision=''), workbook=workbook('UPDATED'))
        result = self.endpoint.execute(request)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        operator = CentralOperator(self.root, self.personnel)
        self.assertEqual(operator.lookup('999002')[0].surname, 'UPDATED')
        self.assertEqual(self.personnel.read_bytes(), self.original_workbook)
        self.assertNotEqual(request.workbook, self.original_workbook)
        self.assertEqual(self.endpoint.execute(request).event, result.event)
        stale = replace(self.command('PERSONNEL_IMPORT', expected_revision=''), workbook=workbook('STALE'))
        self.assertEqual(self.endpoint.execute(stale).status, 'NOT_COMMITTED')
        self.assertEqual(operator.lookup('999002')[0].surname, 'UPDATED')
        self.assertEqual(list(self.directory.rglob('position_outbox.sqlite3')), [])

    def test_lost_shift_mirror_does_not_lose_accepted_shift_or_audit(self):
        request = self.command('SHIFT_START')
        with patch.object(SharedEventStore, '_atomic_json', side_effect=OSError('synthetic mirror outage')):
            result = self.endpoint.execute(request)
            self.assertEqual(result.status, 'CONFIRMED', result.message)
        self.assertEqual(self.store().current_shift()['shift_id'], result.event['result']['shift_id'])
        self.assertEqual(self.endpoint.execute(request).event, result.event)

    def test_same_id_different_intent_never_changes_accepted_record(self):
        request, event = self.start()
        changed = replace(request, values_json=json.dumps({**request.values, 'position': '2'}))
        self.assertEqual(self.endpoint.execute(changed).status, 'UNKNOWN')
        self.assertEqual(self.store().get_active('999002')['event_id'], event['event_id'])
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_official_message_is_central_and_has_declared_actor_receipt(self):
        request = self.command('MESSAGE', targets=['SYNTHETIC_CLIENT'], text='Synthetic official message')
        result = self.endpoint.execute(request)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        self.assertEqual(len(self.store().pending_messages('SYNTHETIC_CLIENT')), 1)
        self.assertEqual(self.endpoint.execute(request).event, result.event)
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_end_receipt_outage_preserves_atomic_end_and_actor(self):
        _, event = self.start()
        original = OfficerStore._atomic_json
        def fail_receipt(store, path, payload):
            if path.parent == store.pending_index:
                raise OSError('synthetic END receipt projection outage')
            return original(store, path, payload)
        request = self.command('REMOTE_END', agms='999002', expected_start_id=event['event_id'],
            when=(self.base+timedelta(minutes=1)).isoformat(), reason='Confirmed remote end')
        with patch.object(OfficerStore, '_atomic_json', fail_receipt):
            result = self.endpoint.execute(request)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        self.assertIsNone(self.store().get_active('999002'))
        self.assertEqual(len(self.store().search_personnel_sessions()), 1)
        self.assertEqual(self.store().officer_action(request.action_id)['before']['event_id'], event['event_id'])

    def test_correction_head_failure_rolls_back_its_audit_too(self):
        _, event = self.start()
        store = self.store()
        with store._shift_db_connect() as db:
            db.execute("CREATE TRIGGER fail_head BEFORE INSERT ON officer_start_heads BEGIN SELECT RAISE(ABORT,'synthetic head outage'); END")
        request = self.command('CORRECT_START', agms='999002', expected_start_id=event['event_id'],
            expected_timestamp=event['timestamp'], new_time=(self.base-timedelta(minutes=1)).isoformat(), reason='Correction head fault')
        self.assertEqual(self.endpoint.execute(request).status, 'NOT_COMMITTED')
        self.assertIsNone(store.officer_action(request.action_id))
        self.assertEqual(store.get_active('999002')['timestamp'], event['timestamp'])
        with store._shift_db_connect() as db:
            db.execute('DROP TRIGGER fail_head')
        self.assertEqual(self.endpoint.execute(request).status, 'CONFIRMED')

    def test_two_roster_publishers_cannot_silently_overwrite_each_other(self):
        requests = [replace(self.command('PERSONNEL_IMPORT', expected_revision=''), workbook=workbook(name))
                    for name in ('FIRST_NEW', 'SECOND_NEW')]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.endpoint.execute, requests))
        self.assertEqual(sum(r.status == 'CONFIRMED' for r in results), 1)
        winner = results.index(next(r for r in results if r.status == 'CONFIRMED'))
        self.assertEqual(CentralOperator(self.root,self.personnel).lookup('999002')[0].surname,
                         ('FIRST_NEW','SECOND_NEW')[winner])
        self.assertEqual(len(self.store().officer_history()), 1)

    def test_invalid_roster_never_replaces_confirmed_central_list(self):
        request = replace(self.command('PERSONNEL_IMPORT', expected_revision=''), workbook=b'INVALID SYNTHETIC ZIP')
        self.assertEqual(self.endpoint.execute(request).status, 'NOT_COMMITTED')
        self.assertEqual(CentralOperator(self.root,self.personnel).lookup('999002')[0].surname, 'TARGET')
        self.assertEqual(self.store().officer_history(), [])

    def test_five_original_identity_checks_are_retained_byte_for_byte(self):
        import hashlib
        import importlib.util
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('mandatory_runner', root/'tools'/'run_regressions.py')
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        expected = {'central_officer_authorization_regression.py':
                    '7d5c4dd410014a5b33d38cf0b97c444fb3584b0b3a159d4b294181dc347204c6'}
        self.assertEqual(runner.HISTORICAL, expected)
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((root/'tests'/name).read_bytes()).hexdigest(), digest)
        proof = 'AssertionError: UNAUTHORIZED_OFFICER_ACTION_ACCEPTED:\n'*5 + 'FAILED (failures=5)'
        self.assertTrue(runner.retired_property_failure(1, proof))
        self.assertFalse(runner.retired_property_failure(124, proof))
        self.assertFalse(runner.retired_property_failure(1, 'ImportError: broken runtime'))
        self.assertFalse(runner.retired_property_failure(1, proof.replace('failures=5','failures=4, errors=1')))


if __name__ == '__main__':
    unittest.main()

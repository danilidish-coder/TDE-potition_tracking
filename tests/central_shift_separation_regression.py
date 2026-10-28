"""D1: officer membership/report boundaries never mutate physical work."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore
from position_tracking_store_io import BusyError


class ShiftSeparation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-d1-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.store = SharedEventStore(self.temp.name)
        self.worker = PersonnelRecord('999001', 'TEST', 'WORKER', 'SYNTHETIC')
        self.next = PersonnelRecord('999002', 'TEST', 'NEXT', 'SYNTHETIC')
        self.officer = PersonnelRecord('999099', 'TEST', 'OFFICER', 'SYNTHETIC')
        self.base = datetime.now().replace(microsecond=0) - timedelta(hours=2)
        self.start = self.store.start(self.worker, '1', 'ΕΙΣΟΔΟΣ', when=self.base, event_id='physical-start')

    def physical(self):
        return {
            'tables': {name: self.store._position_rows('SELECT * FROM ' + name) for name in
                       ('position_operations', 'position_live', 'personnel_sessions', 'position_handovers')},
            'events': {str(p): p.read_bytes() for p in self.store.events.rglob('*.json')},
            'active': self.store.active_all(),
        }

    def shift(self):
        return self.store.start_officer_shift(self.officer, when=self.base + timedelta(minutes=1))

    def close_shift(self, shift):
        return self.store.end_officer_shift(self.officer, when=self.base + timedelta(hours=1),
                                            expected_shift_id=shift['shift_id'])

    def test_open_exclude_undo_close_and_next_shift_preserve_exact_physical_state(self):
        before = self.physical()
        shift = self.shift()
        for state in ('EXCLUDED', 'APPROVED', 'EXCLUDED', 'APPROVED'):
            self.store.set_shift_member_state(self.worker.agms, state)
            self.assertEqual(self.physical(), before)
        final = self.close_shift(shift)
        self.assertEqual(final['closed_active_agms'], [])
        self.assertEqual(self.physical(), before)
        other = PersonnelRecord('999098', 'TEST', 'NEXT', 'OFFICER')
        with patch.dict(os.environ, {'USERNAME': 'ANOTHER_SYNTHETIC_WINDOWS_USER'}):
            reopened = SharedEventStore(self.temp.name)
            reopened.start_officer_shift(other, when=self.base + timedelta(hours=1, minutes=1))
            self.assertEqual(reopened.close_previous_windows_user_positions('BOOTH', 'OTHER'), [])
        self.assertEqual(self.physical(), before)
        self.assertEqual(self.store.get_shift(final['shift_id']), final)

    def test_membership_can_be_decided_before_actual_start(self):
        shift = self.store.start_officer_shift(self.officer, when=self.base + timedelta(minutes=1),
            initial_approved=[self.next.agms], initial_excluded=[self.worker.agms])
        self.assertEqual(shift['approved'], [self.next.agms])
        self.assertIsNone(self.store.get_active(self.next.agms))
        event = self.store.start(self.next, '2', 'ΕΞΟΔΟΣ', when=self.base + timedelta(minutes=2))
        self.assertEqual(self.store.current_shift(), shift)
        self.store.set_shift_member_state(self.next.agms, 'EXCLUDED')
        self.store.set_shift_member_state(self.next.agms, 'APPROVED')
        self.assertEqual(self.store.get_active(self.next.agms)['event_id'], event['event_id'])

    def test_short_completed_work_is_discovered_without_automatic_start_sync(self):
        self.shift()
        event = self.store.start(self.next, '2', 'ΕΞΟΔΟΣ', when=self.base + timedelta(minutes=2))
        self.store.end(self.next, when=self.base + timedelta(minutes=3), expected_start_event_id=event['event_id'])
        self.assertNotIn(self.next.agms, self.store.current_shift()['approved'])
        shift = self.store.sync_active_shift()
        self.assertIn(self.next.agms, shift['pending'])
        shift = self.store.set_shift_member_state(self.next.agms, 'APPROVED')
        rows = self.store.shift_sessions_v2(shift)
        self.assertTrue(any(row['start']['event_id'] == event['event_id'] and row['end'] for row in rows))

    def test_position_start_and_end_finish_while_shift_control_is_held(self):
        self.shift()
        with self.store.officer_lock('__SHIFT_CONTROL__'):
            with ThreadPoolExecutor(max_workers=1) as pool:
                # Default and legacy explicit sync_shift=True must both be independent.
                event = pool.submit(self.store.start, self.next, '2', 'ΕΞΟΔΟΣ').result(timeout=3)
                ended = pool.submit(self.store.end, self.next,
                    expected_start_event_id=event['event_id']).result(timeout=3)
        self.assertEqual(ended['start_event_id'], event['event_id'])
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], self.start['event_id'])

    def test_finalize_ignores_stale_live_preview_but_rejects_wrong_shift(self):
        shift = self.shift()
        self.store.end(self.worker, when=self.base + timedelta(minutes=2))
        new = self.store.start(self.worker, '3', 'ΕΞΟΔΟΣ', when=self.base + timedelta(minutes=3))
        before = self.physical()
        with self.assertRaises(BusyError):
            self.store.end_officer_shift(self.officer, expected_shift_id='wrong-shift')
        final = self.store.end_officer_shift(self.officer, expected_shift_id=shift['shift_id'],
            expected_active_start_ids={self.worker.agms: self.start['event_id']})
        self.assertEqual(final['status'], 'FINALIZED')
        self.assertEqual(self.physical(), before)
        self.assertEqual(self.store.get_active(self.worker.agms)['event_id'], new['event_id'])

    def test_finalized_work_survives_later_actual_end_and_reopen(self):
        final = self.close_shift(self.shift())
        expected = self.store.shift_sessions_v2(final)
        self.assertEqual(len(expected), 1)
        self.assertIsNone(expected[0]['end'])
        self.assertEqual(expected[0]['end_dt'], self.base + timedelta(hours=1))
        ended = self.store.end(self.worker, when=self.base + timedelta(hours=1, minutes=10))
        reopened = SharedEventStore(self.temp.name)
        self.assertEqual(reopened.shift_sessions_v2(reopened.get_shift(final['shift_id'])), expected)
        history = reopened.search_personnel_sessions()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['end_event_id'], ended['event_id'])
        self.assertEqual(history[0]['end_at'], ended['timestamp'])

    def test_failed_finalization_storage_does_not_end_or_alter_any_position(self):
        shift = self.shift()
        before = self.physical()
        with patch.object(self.store, '_store_shift_snapshot', side_effect=OSError('synthetic share outage')):
            with self.assertRaises(OSError):
                self.close_shift(shift)
        self.assertEqual(self.physical(), before)
        self.assertEqual(self.store.current_shift()['status'], 'ACTIVE')
        self.close_shift(shift)
        self.assertEqual(self.physical(), before)

    def test_lost_finalization_mirror_ack_keeps_confirmed_physical_work(self):
        shift = self.shift()
        before = self.physical()
        original = self.store._atomic_json
        def lost_ack(path, value):
            original(path, value)
            if path == self.store._current_shift_path() and value['status'] == 'FINALIZED':
                raise OSError('synthetic lost mirror ACK')
        with patch.object(self.store, '_atomic_json', lost_ack):
            with self.assertRaises(OSError):
                self.close_shift(shift)
        reopened = SharedEventStore(self.temp.name)
        self.assertIsNone(reopened.current_shift())
        self.assertEqual(reopened.get_shift(shift['shift_id'])['status'], 'FINALIZED')
        self.assertEqual(self.physical(), before)

    def test_slow_shift_persistence_does_not_serialize_physical_operations(self):
        shift = self.shift()
        other = SharedEventStore(self.temp.name)
        entered, release = threading.Event(), threading.Event()
        original = self.store._store_shift_snapshot
        def slow(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(8))
            return original(*args, **kwargs)
        with patch.object(self.store, '_store_shift_snapshot', slow), ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(self.close_shift, shift)
            try:
                self.assertTrue(entered.wait(3))
                event = pool.submit(other.start, self.next, '2', 'ΕΞΟΔΟΣ').result(timeout=3)
            finally:
                release.set()
            final = future.result(timeout=3)
        self.assertEqual(final['status'], 'FINALIZED')
        self.assertEqual(other.get_active(self.next.agms)['event_id'], event['event_id'])
        self.assertEqual(other.get_active(self.worker.agms)['event_id'], self.start['event_id'])

    def test_pending_members_still_require_an_officer_decision(self):
        shift = self.shift()
        self.store.start(self.next, '2', 'ΕΞΟΔΟΣ', when=self.base + timedelta(minutes=2))
        before = self.physical()
        with self.assertRaises(ValueError):
            self.close_shift(shift)
        self.assertEqual(self.physical(), before)
        self.store.set_shift_member_state(self.next.agms, 'EXCLUDED')
        self.close_shift(shift)
        self.assertEqual(self.physical(), before)

    def test_old_membership_decision_cannot_change_the_next_shift(self):
        old = self.shift()
        self.close_shift(old)
        new = self.store.start_officer_shift(self.officer, when=self.base + timedelta(hours=1, minutes=1))
        before = self.physical()
        with self.assertRaises(BusyError):
            self.store.set_shift_member_state(self.worker.agms, 'EXCLUDED', expected_shift_id=old['shift_id'])
        self.assertEqual(self.store.current_shift(), new)
        self.assertEqual(self.physical(), before)


if __name__ == '__main__':
    unittest.main()

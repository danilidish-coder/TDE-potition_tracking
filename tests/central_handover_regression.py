"""Phase C: real central SQL transactions, synthetic data and explicit fault boundaries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import json
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore
from position_tracking_store_io import BusyError


class HandoverContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-handover-')
        self.addCleanup(self.temp.cleanup)
        self.store = SharedEventStore(self.temp.name)
        self.old = PersonnelRecord('999001', 'TEST', 'PREVIOUS', 'SYNTHETIC')
        self.new = PersonnelRecord('999002', 'TEST', 'NEXT', 'SYNTHETIC')
        self.third = PersonnelRecord('999003', 'TEST', 'THIRD', 'SYNTHETIC')
        self.when = datetime.now().replace(microsecond=0) - timedelta(minutes=5)
        self.original = self.store.start(self.old, '1', 'ΕΙΣΟΔΟΣ', when=self.when, event_id='original-start')

    def handover(self, store=None, person=None, operation='handover-new', expected='original-start'):
        return (store or self.store).handover(person or self.new, '1', 'ΕΞΟΔΟΣ', expected, operation,
                                              when=self.when + timedelta(minutes=1))

    def reopen(self):
        self.store = SharedEventStore(self.temp.name)
        return self.store

    def assert_transfer(self):
        active = self.store.active_all()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['agms'], self.new.agms)
        self.assertIsNone(self.store.get_active(self.old.agms))
        receipt = self.store.handover_receipt('handover-new')
        self.assertEqual(receipt['start']['timestamp'], receipt['end']['timestamp'])
        self.assertEqual(receipt['start']['timestamp'], (self.when + timedelta(minutes=1)).isoformat())
        self.assertNotEqual(receipt['start']['event_id'], receipt['end']['event_id'])
        self.assertEqual(receipt['end']['start_event_id'], self.original['event_id'])
        self.assertEqual(receipt['actor']['agms'], self.new.agms)
        self.assertTrue(receipt['actor']['windows_user'])
        self.assertTrue(receipt['reason'])
        history = self.store.search_personnel_sessions(person_query=self.old.agms)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['end_event_id'], receipt['end']['event_id'])
        self.assertEqual(len(self.store.iter_all_events()), 3)

    def test_atomic_transfer_timestamp_history_and_audit_survive_reopen(self):
        self.handover()
        self.reopen()
        self.assert_transfer()

    def test_same_id_retry_preserves_original_receipt(self):
        event = self.handover()
        replay = self.store.handover(self.new, '1', 'ΕΞΟΔΟΣ', 'original-start', 'handover-new',
                                    when=self.when + timedelta(days=1), reason='different retry text')
        self.assertEqual(replay, event)
        self.assert_transfer()

    def test_id_collision_cannot_change_intent(self):
        self.handover()
        with self.assertRaises(BusyError):
            self.handover(person=self.third)
        self.assert_transfer()

    def test_old_occupant_ended_or_changed_rejects_stale_confirmation(self):
        self.store.end(self.old, when=self.when + timedelta(seconds=20))
        self.store.start(self.third, '1', 'ΕΞΟΔΟΣ', when=self.when + timedelta(seconds=30), event_id='third-start')
        with self.assertRaises(ValueError):
            self.handover()
        self.assertEqual(self.store.get_active(self.third.agms)['event_id'], 'third-start')
        self.assertIsNone(self.store.get_active(self.new.agms))
        self.assertIsNone(self.store.handover_receipt('handover-new'))

    def test_new_person_already_active_is_unchanged(self):
        self.store.start(self.new, '2', 'ΕΞΟΔΟΣ', when=self.when)
        before = self.store.iter_all_events()
        with self.assertRaises(ValueError):
            self.handover()
        self.assertEqual(self.store.iter_all_events(), before)
        self.assertEqual(len(self.store.active_all()), 2)

    def test_transaction_failure_between_end_and_start_rolls_back_everything(self):
        with self.store._shift_db_connect() as db:
            db.execute("""CREATE TRIGGER fail_handover_start BEFORE INSERT ON position_operations
                WHEN NEW.event_id='handover-new' BEGIN SELECT RAISE(ABORT,'synthetic interruption'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.handover()
        self.reopen()
        self.assertEqual(self.store.get_active(self.old.agms)['event_id'], 'original-start')
        self.assertEqual(len(self.store.iter_all_events()), 1)
        self.assertEqual(self.store.search_personnel_sessions(), [])
        self.assertEqual(self.store._position_rows("SELECT * FROM position_operations WHERE kind='END'"), [])

    def test_projection_outage_keeps_canonical_live_history_and_report_events(self):
        def unavailable(*args):
            raise OSError('synthetic lost share')
        self.store._atomic_json = unavailable
        self.handover()
        self.assert_transfer()
        self.assertEqual(len(self.store.iter_events(self.when, self.when + timedelta(minutes=2))), 3)
        self.reopen()
        self.assert_transfer()
        self.assertEqual(self.store._position_rows('SELECT mirrored FROM position_handovers')[0]['mirrored'], 1)

    def test_ambiguous_commit_ack_is_read_back_without_another_transfer(self):
        original = self.store._commit_handover
        def lost_ack(*args):
            original(*args)
            raise OSError('synthetic commit ACK lost')
        self.store._commit_handover = lost_ack
        with self.assertRaises(OSError):
            self.handover()
        self.reopen()
        self.handover()
        self.assert_transfer()

    def test_fifteen_clients_have_only_one_winner_for_exact_confirmed_start(self):
        def replace(i):
            store = SharedEventStore(self.temp.name)
            person = PersonnelRecord(str(900000+i), 'TEST', 'RACE', str(i))
            try:
                return self.handover(store, person, 'race-'+str(i))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=15) as pool:
            winners = [value for value in pool.map(replace, range(15)) if value]
        self.assertEqual(len(winners), 1)
        self.reopen()
        self.assertEqual(len(self.store.active_all()), 1)
        self.assertEqual(len(self.store.iter_all_events()), 3)
        self.assertEqual(len(self.store.search_personnel_sessions()), 1)

    def test_late_worker_before_transaction_cannot_replace_newer_person(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = self.store._commit_handover
        def delayed(*args):
            entered.set()
            self.assertTrue(release.wait(10))
            return original(*args)
        self.store._commit_handover = delayed
        # Model the old SMB session losing its server locks while Python lives.
        from central_stale_worker_regression import lost_server_lock
        self.store.officer_lock = lost_server_lock
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.handover)
            try:
                self.assertTrue(entered.wait(3))
                other = SharedEventStore(self.temp.name)
                self.handover(other, self.third, 'winning-handover')
            finally:
                release.set()
            with self.assertRaises(ValueError):
                future.result(timeout=5)
        self.reopen()
        self.assertEqual(self.store.active_all()[0]['agms'], self.third.agms)
        self.assertEqual(len(self.store.iter_all_events()), 3)

    def test_late_projection_and_old_retry_never_resurrect_replaced_person(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = self.store._mirror_handover
        def delayed(receipt):
            entered.set()
            self.assertTrue(release.wait(10))
            original(receipt)
        self.store._mirror_handover = delayed
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.handover)
            try:
                self.assertTrue(entered.wait(3))
                other = SharedEventStore(self.temp.name)
                other.handover(self.third, '1', 'ΕΙΣΟΔΟΣ', 'handover-new', 'third-handover',
                               when=self.when + timedelta(minutes=2))
            finally:
                release.set()
            future.result(timeout=5)
        self.reopen()
        self.handover()  # Original receipt only; never reapply its live claim.
        self.assertEqual(self.store.active_all()[0]['agms'], self.third.agms)
        self.assertEqual(len(self.store.iter_all_events()), 5)
        self.assertEqual(len(self.store.search_personnel_sessions()), 2)

    def test_process_death_after_atomic_commit_recovers(self):
        self.crash('committed', 77)
        self.assert_transfer()

    def test_reader_sees_old_or_new_occupant_never_partial_transaction(self):
        reader = SharedEventStore(self.temp.name)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        original = self.store._upsert_personnel_session_con
        def paused(*args):
            original(*args)
            entered.set()
            self.assertTrue(release.wait(10))
        self.store._upsert_personnel_session_con = paused
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.handover)
            try:
                self.assertTrue(entered.wait(3))
                active = reader.active_all()
                self.assertEqual(len(active), 1)
                self.assertEqual(active[0]['event_id'], 'original-start')
                self.assertEqual(reader.search_personnel_sessions(), [])
            finally:
                release.set()
            future.result(timeout=5)
        self.assert_transfer()

    def test_same_second_chain_preserves_each_completed_session(self):
        self.store.handover(self.new, '1', 'ΕΞΟΔΟΣ', 'original-start', 'first', when=self.when)
        self.store.handover(self.third, '1', 'ΕΙΣΟΔΟΣ', 'first', 'second', when=self.when)
        report = {'version': 2, 'approved': [self.old.agms, self.new.agms, self.third.agms],
                  'start_at': (self.when - timedelta(seconds=1)).isoformat(),
                  'end_at': (self.when + timedelta(seconds=1)).isoformat()}
        sessions = self.store.shift_sessions_v2(report)
        self.assertEqual(len(sessions), 3)
        self.assertEqual({row['start']['event_id'] for row in sessions if row['end']}, {'original-start', 'first'})
        self.assertEqual(len(self.store.search_personnel_sessions()), 2)
        self.assertEqual(self.store.active_all()[0]['event_id'], 'second')

    def test_handover_between_map_snapshot_and_projection_does_not_hide_both_people(self):
        reader = SharedEventStore(self.temp.name)
        query = reader._position_rows
        fired = []
        def swap_after_snapshot(sql, args=()):
            rows = query(sql, args)
            if 'FROM position_live' in sql and not fired:
                fired.append(True)
                self.handover()
            return rows
        reader._position_rows = swap_after_snapshot
        active = reader.active_all()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]['event_id'], 'original-start')
        self.assertEqual(reader.active_all()[0]['event_id'], 'handover-new')

    def test_process_death_inside_transaction_restores_old_occupant(self):
        self.crash('inside', 78)
        self.assertEqual(self.store.get_active(self.old.agms)['event_id'], 'original-start')
        self.assertEqual(len(self.store.iter_all_events()), 1)
        self.assertEqual(self.store.search_personnel_sessions(), [])

    def crash(self, mode, code):
        program = """
import os,sys
from datetime import datetime
sys.path.insert(0,sys.argv[1])
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord
s=SharedEventStore(sys.argv[2]); original=s._commit_handover
def committed(*args): original(*args); os._exit(77)
if sys.argv[3]=='committed': s._commit_handover=committed
else: s._upsert_personnel_session_con=lambda *args: os._exit(78)
s.handover(PersonnelRecord('999002','TEST','NEXT','SYNTHETIC'),'1','ΕΞΟΔΟΣ',
           'original-start','handover-new',when=datetime.fromisoformat(sys.argv[4]))
"""
        source = Path(__file__).resolve().parents[1] / 'src'
        done = subprocess.run([sys.executable, '-c', program, str(source), self.temp.name, mode,
                               (self.when + timedelta(minutes=1)).isoformat()],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, code, done.stderr)
        self.reopen()


if __name__ == '__main__':
    unittest.main()

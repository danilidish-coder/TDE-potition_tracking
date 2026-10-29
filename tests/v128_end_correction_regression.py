"""v1.2.8c: ο ΑΞΥΠ διορθώνει την ώρα ΛΗΞΗΣ θέσης που έχει ήδη κλείσει (π.χ. ΛΗΞΗ 17:00 → 14:00)."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_officer import CentralOfficer, OfficerRequest, describe_history
from position_tracking_officer_store import OfficerStore
from position_tracking_report_text import session_marker
from central_officer_regression import workbook


class EndTimeCorrection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-v128c-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '.tde_runtime'; self.root.mkdir()
        (self.root / 'personnel.xlsx').write_bytes(workbook())
        self.endpoint = CentralOfficer(self.root, self.root / 'personnel.xlsx')
        self.now = datetime.now().replace(second=0, microsecond=0)

    def iso(self, **delta):
        return (self.now - timedelta(**delta)).isoformat(timespec='seconds')

    def act(self, action, **values):
        request = OfficerRequest(action, '999001', json.dumps(values), True)
        return self.endpoint.execute(request)

    def ok(self, action, **values):
        result = self.act(action, **values)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        return result

    def late_end(self, agms='999002', position='3', started=300, ended=30):
        """Έγινε ΕΝΑΡΞΗ και ΛΗΞΗ· η ΛΗΞΗ πατήθηκε πολύ αργά."""
        self.ok('REMOTE_START', agms=agms, position=position, direction='ΕΙΣΟΔΟΣ', when=self.iso(minutes=started), reason='start')
        active = OfficerStore(self.root).get_active(agms)
        self.ok('REMOTE_END', agms=agms, expected_start_id=active['event_id'], when=self.iso(minutes=ended), reason='late end')
        return active['event_id']

    def session(self, agms='999002'):
        return next(s for s in self.endpoint.snapshot('999001')['recent_sessions'] if s['agms'] == agms)

    def correct(self, session, minutes_ago, reason='Η ΛΗΞΗ πατήθηκε αργά', **extra):
        values = dict(agms=session['agms'], position=session['position'], expected_start_id=session['start_event_id'],
                      expected_end_id=session['end_event_id'], expected_timestamp=session['end_at'],
                      new_time=self.iso(minutes=minutes_ago), reason=reason)
        values.update(extra)
        return self.act('CORRECT_END', **values)

    def test_late_end_is_corrected_everywhere(self):
        start_id = self.late_end(started=300, ended=30)
        before = self.session()
        self.assertEqual(before['end_at'], self.iso(minutes=30))
        result = self.correct(before, 180)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        store = OfficerStore(self.root)
        # Λίστα εργασιών (ιστορικό, στατιστικά, έλεγχοι επικάλυψης)
        row = next(r for r in store.search_personnel_sessions(person_query='999002'))
        self.assertEqual(row['end_at'], self.iso(minutes=180))
        self.assertEqual(row['duration_seconds'], 120 * 60)
        self.assertEqual(self.session()['end_at'], self.iso(minutes=180))
        # Αναφορές: το γεγονός ΛΗΞΗΣ δείχνει τη νέα ώρα και ότι διορθώθηκε
        events = store.iter_events(self.now - timedelta(hours=8), self.now + timedelta(hours=1))
        end = next(e for e in events if e['kind'] == 'END')
        self.assertEqual(end['timestamp'], self.iso(minutes=180))
        self.assertEqual(end['original_timestamp'], self.iso(minutes=30))
        start = next(e for e in events if e['kind'] == 'START' and e['event_id'] == start_id)
        self.assertIn('ΔΙΟΡΘΩΜΕΝΗ', session_marker(dict(start=start, end=end)))
        # Η αρχική ΛΗΞΗ μένει αναλλοίωτη στο κεντρικό αρχείο
        raw = store._position_rows("SELECT payload FROM position_operations WHERE kind='END'")
        self.assertEqual(json.loads(raw[0]['payload'])['timestamp'], self.iso(minutes=30))
        # Ιστορικό ΑΞΥΠ
        text = describe_history(self.endpoint.history('999001'))
        self.assertIn('Διόρθωση ώρας ΛΗΞΗΣ', text)
        self.assertIn('Η ΛΗΞΗ πατήθηκε αργά', text)

    def test_correction_frees_the_position_for_the_next_person(self):
        self.late_end(started=300, ended=30)
        clash = self.endpoint.conflicts('999001', 'REMOTE_START', dict(
            agms='999003', position='3', when=self.iso(minutes=120)))
        self.assertTrue(any('κατειλημμένη' in w for w in clash['warnings']), clash)
        self.assertEqual(self.correct(self.session(), 180).status, 'CONFIRMED')
        clash = self.endpoint.conflicts('999001', 'REMOTE_START', dict(
            agms='999003', position='3', when=self.iso(minutes=120)))
        self.assertFalse(any('κατειλημμένη' in w for w in clash['warnings']), clash)

    def test_extending_the_end_warns_about_the_overlap(self):
        self.late_end(started=300, ended=180)
        self.late_end(agms='999003', started=150, ended=60)
        mine = self.session('999002')
        check = self.endpoint.conflicts('999001', 'CORRECT_END', dict(
            agms='999002', position='3', expected_start_id=mine['start_event_id'],
            expected_end_id=mine['end_event_id'], expected_timestamp=mine['end_at'], new_time=self.iso(minutes=90)))
        self.assertEqual(check['errors'], [])
        self.assertTrue(any('κατειλημμένη' in w and 'THIRD' in w for w in check['warnings']), check)

    def test_refusals_leave_everything_unchanged(self):
        self.late_end(started=300, ended=30)
        mine = self.session()
        for minutes_ago, reason, expected in ((320, 'Πριν την ΕΝΑΡΞΗ', 'έπεται'), (-40, 'Στο μέλλον', 'μελλοντική'),
                                                (30, 'Ίδια ώρα', 'ίδια'), (180, 'abc', 'αιτιολογία')):
            result = self.correct(mine, minutes_ago, reason=reason)
            self.assertEqual(result.status, 'NOT_COMMITTED', (reason, result.message))
            self.assertIn(expected, result.message)
        self.assertEqual(self.session()['end_at'], self.iso(minutes=30))
        # Μια δεύτερη διόρθωση πρέπει να ξεκινά από την τρέχουσα ώρα· η παλιά εικόνα απορρίπτεται.
        self.assertEqual(self.correct(mine, 180).status, 'CONFIRMED')
        stale = self.correct(mine, 200)
        self.assertEqual(stale.status, 'NOT_COMMITTED')
        self.assertEqual(self.correct(self.session(), 200).status, 'CONFIRMED')
        self.assertEqual(self.session()['end_at'], self.iso(minutes=200))

    def test_index_rebuild_keeps_the_corrected_end(self):
        self.late_end(started=300, ended=30)
        self.assertEqual(self.correct(self.session(), 180).status, 'CONFIRMED')
        store = OfficerStore(self.root)
        events = store.iter_all_events()
        start = next(e for e in events if e['kind'] == 'START')
        raw_end = dict(next(e for e in events if e['kind'] == 'END'), timestamp=self.iso(minutes=30))
        raw_end.pop('original_timestamp', None)
        with store._shift_db_write_lock(), store._shift_db_connect() as db:
            store._upsert_personnel_session_con(db, start, raw_end)
        self.assertEqual(self.session()['end_at'], self.iso(minutes=180))

    def test_open_position_is_not_an_end_correction(self):
        self.ok('REMOTE_START', agms='999002', position='5', direction='ΕΞΟΔΟΣ', when=self.iso(minutes=40), reason='open position')
        self.assertEqual([s for s in self.endpoint.snapshot('999001')['recent_sessions']], [])


if __name__ == '__main__':
    unittest.main()

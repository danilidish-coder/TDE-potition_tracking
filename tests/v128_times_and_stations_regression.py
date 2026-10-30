"""v1.2.8: European dates, station labels, chosen shift/remote times and their corrections."""
from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from position_tracking_common import format_day, format_when, parse_day, parse_when
from position_tracking_officer import CentralOfficer, OfficerRequest, describe_history, station_labels
from position_tracking_officer_store import OfficerStore
from position_tracking_report_text import session_marker, shift_correction_note
from central_officer_regression import workbook


class EuropeanDates(unittest.TestCase):
    def test_format_and_parse_round_trip(self):
        self.assertEqual(format_when('2026-10-29T18:05:09'), '29/10/2026 18:05')
        self.assertEqual(format_when('2026-10-29T18:05:09', seconds=True), '29/10/2026 18:05:09')
        self.assertEqual(format_when(''), '')
        self.assertEqual(format_day('2026-10-29T18:05:09'), '29/10/2026')
        self.assertEqual(parse_when('29/10/2026 18:05'), datetime(2026, 10, 29, 18, 5))
        self.assertEqual(parse_when('29/10/2026 18:05:30'), datetime(2026, 10, 29, 18, 5, 30))
        self.assertEqual(parse_when('2026-10-29 18:05:30'), datetime(2026, 10, 29, 18, 5, 30))
        self.assertEqual(parse_day('29/10/2026').isoformat(), '2026-10-29')
        with self.assertRaises(ValueError):
            parse_when('31/02/2026 10:00')
        with self.assertRaises(ValueError):
            parse_day('hello')


class StationLabels(unittest.TestCase):
    def test_latest_open_start_per_station_and_free_station(self):
        clients = [dict(client_id='c1', computer='ΣΤΑΘΜΟΣ-3', user='u3'),
                   dict(client_id='c2', computer='ΣΤΑΘΜΟΣ-4', user='u4')]
        active = [
            dict(agms='1', surname='Παπαδόπουλος', given_name='Γεώργιος', position='2', timestamp='2026-10-29T08:00:00',
                 computer='σταθμος-3', user='U3'),
            dict(agms='2', surname='Παπαδόπουλος', given_name='Γεώργιος', position='5', timestamp='2026-10-29T09:00:00',
                 computer='ΣΤΑΘΜΟΣ-3', user='u3'),
            dict(agms='3', surname='ΑΞΥΠ', given_name='Χ', position='7', timestamp='2026-10-29T10:00:00',
                 computer='ΣΤΑΘΜΟΣ-4', user='u4', declared_action=dict(action='REMOTE_START')),
        ]
        labels = station_labels(clients, active)
        self.assertEqual(labels['c1'], 'ΣΤΑΘΜΟΣ-3 — Παπαδόπουλος Γ. — Θέση 5')
        self.assertEqual(labels['c2'], 'ΣΤΑΘΜΟΣ-4 — (ελεύθερος)')


class OfficerTimes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tde-v128-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.root = self.directory / '.tde_runtime'; self.root.mkdir()
        (self.root / 'personnel.xlsx').write_bytes(workbook())
        self.endpoint = CentralOfficer(self.root, self.root / 'personnel.xlsx')
        self.now = datetime.now().replace(microsecond=0)

    def run_action(self, action, **values):
        request = OfficerRequest(action, '999001', json.dumps(values), True)
        return self.endpoint.execute(request), request

    def ok(self, action, **values):
        result, request = self.run_action(action, **values)
        self.assertEqual(result.status, 'CONFIRMED', result.message)
        return result, request

    def iso(self, **delta):
        return (self.now - timedelta(**delta)).isoformat(timespec='seconds')

    def test_snapshot_exposes_station_labels_and_recent_starts(self):
        self.ok('REMOTE_START', agms='999002', position='3', direction='ΕΙΣΟΔΟΣ', when=self.iso(minutes=30), reason='remote start')
        store = OfficerStore(self.root)
        store.write_client_heartbeat('client-1')
        state = self.endpoint.snapshot('999001')
        self.assertIn('client-1', state['station_labels'])
        self.assertIn('(ελεύθερος)', state['station_labels']['client-1'])  # officer remote starts belong to no station
        self.assertEqual([s['agms'] for s in state['recent_starts']], ['999002'])

    def test_shift_start_time_and_pending_people_since_that_time(self):
        self.ok('REMOTE_START', agms='999002', position='1', direction='ΕΙΣΟΔΟΣ', when=self.iso(hours=2), reason='worked earlier')
        active = OfficerStore(self.root).get_active('999002')
        self.ok('REMOTE_END', agms='999002', expected_start_id=active['event_id'], when=self.iso(hours=1), reason='ended earlier')
        chosen = self.iso(hours=3)
        self.ok('SHIFT_START', when=chosen)
        shift = self.endpoint.snapshot('999001')['shift']
        self.assertEqual(shift['start_at'], chosen)
        self.assertIn('999002', shift['pending'])

    def test_shift_times_reject_future_old_and_inverted(self):
        result, _ = self.run_action('SHIFT_START', when=(self.now + timedelta(hours=1)).isoformat())
        self.assertEqual(result.status, 'NOT_COMMITTED'); self.assertIn('μελλοντική', result.message)
        result, _ = self.run_action('SHIFT_START', when=self.iso(hours=30))
        self.assertEqual(result.status, 'NOT_COMMITTED'); self.assertIn('24 ώρες', result.message)
        self.ok('SHIFT_START', when=self.iso(hours=30), confirm_old=True)
        shift = self.endpoint.snapshot('999001')['shift']
        result, _ = self.run_action('SHIFT_END', expected_shift_id=shift['shift_id'], when=self.iso(hours=31))
        self.assertEqual(result.status, 'NOT_COMMITTED')
        result, _ = self.run_action('SHIFT_END', expected_shift_id=shift['shift_id'], when=(self.now + timedelta(hours=1)).isoformat())
        self.assertEqual(result.status, 'NOT_COMMITTED')
        self.ok('SHIFT_END', expected_shift_id=shift['shift_id'], when=self.iso(hours=2))
        finished = OfficerStore(self.root).get_shift(shift['shift_id'])
        self.assertEqual(finished['end_at'], self.iso(hours=2))

    def test_end_time_never_closes_open_positions(self):
        self.ok('REMOTE_START', agms='999002', position='4', direction='ΕΞΟΔΟΣ', when=self.iso(minutes=50), reason='open at shift end')
        self.ok('SHIFT_START', when=self.iso(minutes=45))
        shift = self.endpoint.snapshot('999001')['shift']
        self.ok('SHIFT_END', expected_shift_id=shift['shift_id'], when=self.iso(minutes=5))
        self.assertIsNotNone(OfficerStore(self.root).get_active('999002'))

    def test_shift_time_correction_active_current_and_archived(self):
        self.ok('SHIFT_START', when=self.iso(hours=2))
        shift = self.endpoint.snapshot('999001')['shift']
        # Active shift: start can move earlier, with reason, without touching positions.
        result, request = self.run_action('SHIFT_TIME_CORRECT', shift_id=shift['shift_id'], which='start_at',
                                          new_time=self.iso(hours=3), reason='abc')
        self.assertEqual(result.status, 'NOT_COMMITTED')
        self.ok('SHIFT_TIME_CORRECT', shift_id=shift['shift_id'], which='start_at', new_time=self.iso(hours=3),
                reason='Actual start was earlier')
        corrected = self.endpoint.snapshot('999001')['shift']
        self.assertEqual(corrected['start_at'], self.iso(hours=3))
        self.assertEqual(corrected['time_corrections'][0]['previous'], self.iso(hours=2))
        self.assertEqual(corrected['shift_id'], shift['shift_id'])
        # End can only be corrected after the shift is finalized.
        result, _ = self.run_action('SHIFT_TIME_CORRECT', shift_id=shift['shift_id'], which='end_at',
                                    new_time=self.iso(hours=1), reason='Too early to end')
        self.assertEqual(result.status, 'NOT_COMMITTED')
        self.ok('SHIFT_END', expected_shift_id=shift['shift_id'], when=self.iso(minutes=30))
        self.ok('SHIFT_TIME_CORRECT', shift_id=shift['shift_id'], which='end_at', new_time=self.iso(minutes=20),
                reason='Handover finished later')
        final = OfficerStore(self.root).get_shift(shift['shift_id'])
        self.assertEqual(final['end_at'], self.iso(minutes=20))
        self.assertEqual([c['which'] for c in final['time_corrections']], ['start_at', 'end_at'])
        self.assertIn('έναρξης και λήξης', shift_correction_note(final))
        # An older, archived shift is corrected through its own audited receipt.
        self.ok('SHIFT_START', when=self.iso(minutes=15))
        newer = self.endpoint.snapshot('999001')['shift']
        self.ok('SHIFT_TIME_CORRECT', shift_id=shift['shift_id'], which='start_at', new_time=self.iso(hours=4),
                reason='Archived start was wrong')
        archived = OfficerStore(self.root).get_shift(shift['shift_id'])
        self.assertEqual(archived['start_at'], self.iso(hours=4))
        self.assertEqual(self.endpoint.snapshot('999001')['shift']['shift_id'], newer['shift_id'])
        history = OfficerStore(self.root).officer_history()
        self.assertEqual([h['action'] for h in history].count('SHIFT_TIME_CORRECT'), 3)
        self.assertTrue(all(h['reason'] for h in history if h['action'] == 'SHIFT_TIME_CORRECT'))

    def test_remote_times_validation_conflicts_and_marker(self):
        result, _ = self.run_action('REMOTE_START', agms='999002', position='1', direction='ΕΙΣΟΔΟΣ',
                                    when=(self.now + timedelta(hours=1)).isoformat(), reason='future start')
        self.assertEqual(result.status, 'NOT_COMMITTED')
        # A completed earlier session of another person on booth 6 and one of the same person.
        _, first = self.ok('REMOTE_START', agms='999003', position='6', direction='ΕΙΣΟΔΟΣ', when=self.iso(hours=3), reason='other person')
        other = OfficerStore(self.root).get_active('999003')
        self.ok('REMOTE_END', agms='999003', expected_start_id=other['event_id'], when=self.iso(hours=1), reason='other ended')
        warning = self.endpoint.conflicts('999001', 'REMOTE_START', dict(agms='999002', position='6', when=self.iso(hours=2)))
        self.assertEqual(warning['errors'], [])
        self.assertTrue(any('κατειλημμένη' in text for text in warning['warnings']), warning)
        self.assertEqual(self.endpoint.conflicts('999001', 'REMOTE_START', dict(
            agms='999002', position='6', when=(self.now + timedelta(hours=2)).isoformat()))['errors'],
            ['Η ώρα δεν μπορεί να είναι μελλοντική.'])
        # Same person, repeated work at chosen times.
        _, start = self.ok('REMOTE_START', agms='999002', position='2', direction='ΕΙΣΟΔΟΣ', when=self.iso(hours=3), reason='first work')
        mine = OfficerStore(self.root).get_active('999002')
        self.ok('REMOTE_END', agms='999002', expected_start_id=mine['event_id'], when=self.iso(hours=2), reason='first work ended')
        overlap = self.endpoint.conflicts('999001', 'REMOTE_START', dict(agms='999002', position='9', when=self.iso(hours=2, minutes=30)))
        self.assertTrue(any('ίδιου ατόμου' in text for text in overlap['warnings']), overlap)
        self.ok('REMOTE_START', agms='999002', position='5', direction='ΕΞΟΔΟΣ', when=self.iso(minutes=90), reason='second work')
        sessions = OfficerStore(self.root).search_personnel_sessions(person_query='999002')
        self.assertEqual(len(sessions), 1)
        # Report marker: chosen times differing from the recording time are marked.
        events = [e for e in OfficerStore(self.root).iter_all_events() if e.get('agms') == '999002']
        start_event = next(e for e in events if e['kind'] == 'START' and e['position'] == '2')
        end_event = next(e for e in events if e['kind'] == 'END')
        self.assertEqual(session_marker(dict(start=start_event, end=end_event)), ' (ΔΙΟΡΘΩΜΕΝΗ)')
        self.assertEqual(session_marker(dict(start=dict(position='1'), end=dict())), '')
        self.assertEqual(session_marker(dict(start=dict(historical=True), end=dict())), ' (ΙΣΤΟΡΙΚΗ ΚΑΤΑΧΩΡΙΣΗ)')
        self.assertEqual(session_marker(dict(start=dict(original_timestamp='x'), end=dict())), ' (ΔΙΟΡΘΩΜΕΝΗ)')

    def test_history_is_readable_with_european_dates(self):
        self.ok('REMOTE_START', agms='999002', position='3', direction='ΕΙΣΟΔΟΣ', when=self.iso(minutes=30), reason='visible reason')
        text = describe_history(OfficerStore(self.root).officer_history())
        chosen = (self.now - timedelta(minutes=30)).strftime('%d/%m/%Y %H:%M')
        self.assertIn('Απομακρυσμένη ΕΝΑΡΞΗ', text); self.assertIn(chosen, text); self.assertIn('visible reason', text)
        self.assertNotRegex(text, r'\d{4}-\d{2}-\d{2}')
        self.assertIn('Δεν υπάρχουν', describe_history([]))

    def test_correct_start_rejects_future_time(self):
        self.ok('REMOTE_START', agms='999002', position='1', direction='ΕΙΣΟΔΟΣ', when=self.iso(minutes=30), reason='start then correct')
        active = OfficerStore(self.root).get_active('999002')
        result, _ = self.run_action('CORRECT_START', agms='999002', expected_start_id=active['event_id'],
                                    expected_timestamp=active['timestamp'],
                                    new_time=(self.now + timedelta(hours=2)).isoformat(), reason='future correction')
        self.assertEqual(result.status, 'NOT_COMMITTED')


if __name__ == '__main__':
    unittest.main()

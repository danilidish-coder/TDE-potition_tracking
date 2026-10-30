"""Real Qt Phase C confirmation, cancellation, stale confirmation and recheck."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtWidgets import QApplication, QMessageBox
from position_tracking_central import PositionRequest, UNCONFIRMED
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore
import central_operator_ui_regression as fixture


class HandoverUI(unittest.TestCase):
    wait = fixture.OperatorUI.wait
    destroy_window = staticmethod(fixture.OperatorUI.destroy_window)

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        fixture.OperatorUI.setUp(self)
        self.old = PersonnelRecord('999001', 'TEST', 'SYNTHETIC', 'FIRST')
        self.old_start = SharedEventStore(self.root).start(
            self.old, '1', 'ΕΙΣΟΔΟΣ', when=datetime.now() - timedelta(minutes=5), event_id='old-start')
        self.window.agms_input.setText('999002')
        self.window.direction.setCurrentText('ΕΞΟΔΟΣ')
        self.wait(lambda: self.window.start_btn.isEnabled())

    def snapshot(self):
        store = SharedEventStore(self.root)
        return {table: store._position_rows('SELECT * FROM ' + table) for table in (
            'position_operations', 'position_live', 'personnel_sessions', 'position_handovers')}

    def test_no_changes_no_operation_history_or_live_claim(self):
        before = self.snapshot()
        raw = {str(p): p.read_bytes() for p in self.root.joinpath('events').rglob('*.json')}
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No) as question:
            self.window.start_btn.click()
            self.wait(lambda: self.window._action_future is None and self.window._request is None)
        self.assertEqual(question.call_count, 1)
        self.assertIn(self.old.full_name, question.call_args.args[2])
        self.assertIn('ΕΙΣΟΔΟΣ', question.call_args.args[2])
        self.assertEqual(self.snapshot(), before)
        self.assertEqual({str(p): p.read_bytes() for p in self.root.joinpath('events').rglob('*.json')}, raw)

    def test_yes_is_one_central_transfer_with_matching_full_timestamps(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes) as question:
            self.window.start_btn.click()
            self.wait(lambda: self.window.end_btn.isEnabled())
        self.assertEqual(question.call_count, 1)
        store = SharedEventStore(self.root)
        receipt = json.loads(store._position_rows('SELECT receipt FROM position_handovers')[0]['receipt'])
        self.assertEqual(receipt['start']['timestamp'], receipt['end']['timestamp'])
        self.assertEqual(receipt['end']['agms'], '999001')
        self.assertEqual(receipt['start']['agms'], '999002')
        self.assertEqual(receipt['actor']['agms'], '999002')
        self.assertEqual(len(store.active_all()), 1)
        self.assertEqual(len(store.search_personnel_sessions()), 1)
        self.assertEqual(len(store.iter_all_events()), 3)

    def test_previous_explicit_end_means_ordinary_start_without_question(self):
        SharedEventStore(self.root).end(self.old, expected_start_event_id='old-start')
        with patch.object(QMessageBox, 'question') as question:
            self.window.start_btn.click()
            self.wait(lambda: self.window.end_btn.isEnabled())
        question.assert_not_called()
        self.assertEqual(SharedEventStore(self.root)._position_rows('SELECT * FROM position_handovers'), [])

    def test_old_yes_cannot_replace_person_who_took_booth_during_dialog(self):
        third = PersonnelRecord('999003', 'TEST', 'THIRD', 'SYNTHETIC')
        def answer(*args):
            SharedEventStore(self.root).handover(third, '1', 'ΕΞΟΔΟΣ', 'old-start', 'third-start')
            return QMessageBox.Yes
        with patch.object(QMessageBox, 'question', side_effect=answer):
            self.window.start_btn.click()
            self.wait(lambda: self.window._action_future is None and self.window._request is None)
        store = SharedEventStore(self.root)
        self.assertEqual(store.active_all()[0]['event_id'], 'third-start')
        self.assertIsNone(store.get_active('999002'))
        self.assertEqual(len(store.iter_all_events()), 3)
        self.assertIn('Η θέση άλλαξε', self.window.info.text())

    def test_lost_ack_and_unavailable_readback_keep_request_until_recheck(self):
        original = SharedEventStore._commit_handover
        def lost_ack(store, *args):
            original(store, *args)
            raise OSError('synthetic lost commit ACK')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), \
                patch.object(SharedEventStore, '_commit_handover', lost_ack), \
                patch.object(self.window.endpoint, 'check', side_effect=OSError('synthetic outage')):
            self.window.start_btn.click()
            self.wait(lambda: self.window._action_future is None and self.window._request is not None
                      and bool(self.window._request.handover_start_id))
        request = self.window._request
        self.assertIn(UNCONFIRMED, self.window.info.text())
        self.assertFalse(self.window.start_btn.isEnabled())
        self.assertFalse(self.window.end_btn.isEnabled())
        self.window.recheck_btn.click()
        self.wait(lambda: self.window.end_btn.isEnabled())
        store = SharedEventStore(self.root)
        self.assertEqual(store.active_all()[0]['event_id'], request.operation_id)
        self.assertEqual(len(store.iter_all_events()), 3)


if __name__ == '__main__':
    unittest.main()

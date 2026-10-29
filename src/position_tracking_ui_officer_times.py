"""Officer window: shift start/end times, their later correction and the pre-change check."""
from datetime import datetime, timedelta
from PySide6.QtWidgets import QInputDialog, QMessageBox
from position_tracking_common import format_when


class OfficerTimesMixin:
    def begin_shift(self):
        if not self._state or self._state['shift']:
            return
        state = self._state
        now = datetime.now().replace(second=0, microsecond=0)

        def info(moment):
            if datetime.now() - moment > timedelta(hours=24):
                return 'Η ώρα είναι πάνω από 24 ώρες πίσω: δεν εμφανίζονται οι παλαιότερες ΕΝΑΡΞΕΙΣ.'
            since = moment.isoformat(timespec='seconds')
            starts = [s for s in state.get('recent_starts', []) if s['timestamp'] >= since]
            if not starts:
                return 'Κανείς δεν έχει κάνει ΕΝΑΡΞΗ από αυτή την ώρα.'
            names = sorted({s['full_name'] or s['agms'] for s in starts})
            return (f'ΕΝΑΡΞΗ από αυτή την ώρα έχουν κάνει {len(names)} άτομα: ' + ', '.join(names[:8])
                    + ('…' if len(names) > 8 else '') + '\nΌσοι ΔΕΝ είναι ακόμη ενεργοί θα μπουν σε ΑΝΑΜΟΝΗ για απόφαση.')

        answer = self._ask(self, 'ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ', 'Ώρα έναρξης βάρδιας (προτείνεται η τρέχουσα):', now, info=info)
        if not answer:
            return
        moment = answer['moment']
        previous = next((r for r in state['reports'] if r.get('end_at')), None)
        if previous and previous['end_at'] > moment.isoformat(timespec='seconds'):
            if QMessageBox.question(self, 'Επικάλυψη βαρδιών',
                    f"Η προηγούμενη βάρδια έληξε στις {format_when(previous['end_at'])}, μετά την ώρα που επιλέξατε.\n"
                    'Να συνεχίσω;', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
        self.change('SHIFT_START', when=moment.isoformat(timespec='seconds'), confirm_old=answer['confirm_old'],
                    description=f'Να ξεκινήσει νέα βάρδια στις {format_when(moment)};\n'
                                'Οι πραγματικές θέσεις δεν θα μεταβληθούν.')

    def end_current_shift(self):
        if self._state and self._state['shift']:
            shift = self._state['shift']
            now = datetime.now().replace(second=0, microsecond=0)
            start = datetime.fromisoformat(shift['start_at'])
            answer = self._ask(self, 'ΛΗΞΗ ΒΑΡΔΙΑΣ', 'Ώρα λήξης βάρδιας (προτείνεται η τρέχουσα):', now,
                                minimum=start.replace(second=0), minimum_text='Η λήξη προηγείται της έναρξης της βάρδιας ('
                                + format_when(start) + ').')
            if not answer:
                return
            self.change('SHIFT_END', expected_shift_id=shift['shift_id'], when=answer['moment'].isoformat(timespec='seconds'),
                confirm_old=answer['confirm_old'],
                description=f"Να ολοκληρωθεί η βάρδια στις {format_when(answer['moment'])};\n"
                            'Οι φυσικές θέσεις παραμένουν ενεργές.')

    def correct_shift_time(self):
        """Διόρθωση ώρας έναρξης ή λήξης βάρδιας εκ των υστέρων (τρέχουσα ή επιλεγμένη αναφορά)."""
        if not self._state or self._future is not None or self._request:
            return
        shift = self._state['shift']
        identifier = self.reports.currentData() or (shift or {}).get('shift_id') or \
            (self._state['reports'][0]['shift_id'] if self._state['reports'] else '')
        if not identifier:
            QMessageBox.warning(self, 'Βάρδια', 'Δεν υπάρχει βάρδια για διόρθωση.')
            return
        target = shift if shift and shift['shift_id'] == identifier else next(
            (r for r in self._state['reports'] if r['shift_id'] == identifier), None)
        if not target:
            QMessageBox.warning(self, 'Βάρδια', 'Επιλέξτε βάρδια από τη λίστα αναφορών.')
            return
        finished = bool(target.get('end_at'))
        options = ['Ώρα έναρξης'] + (['Ώρα λήξης'] if finished else [])
        choice = options[0]
        if len(options) > 1:
            choice, ok = QInputDialog.getItem(self, 'Διόρθωση ώρας βάρδιας', 'Ποια ώρα διορθώνεται;', options, 0, False)
            if not ok:
                return
        which = 'start_at' if choice == options[0] else 'end_at'
        current = datetime.fromisoformat(target[which])
        answer = self._ask(self, 'Διόρθωση ώρας βάρδιας',
                            f"{choice} βάρδιας: τώρα {format_when(current)}. Νέα ώρα:", current, reason=True)
        if not answer:
            return
        values = dict(shift_id=str(identifier), which=which, new_time=answer['moment'].isoformat(timespec='seconds'),
                      reason=answer['reason'], confirm_old=answer['confirm_old'])
        self._pending = dict(action='SHIFT_TIME_CORRECT', values=values,
            description=f"Διόρθωση ώρας {choice.lower()} βάρδιας\nΠροηγούμενη: {format_when(current)}\n"
                        f"Νέα: {format_when(answer['moment'])}\nΑιτιολογία: {answer['reason']}\n"
                        'Οι πραγματικές θέσεις δεν αλλάζουν.')
        self.submit('check', self.endpoint.shift_correction_preview, self.officer.text().strip(),
                    values['shift_id'], which, values['new_time'])

    def after_check(self, result):
        """Συνέχεια μετά τον έλεγχο προειδοποιήσεων (ώρα βάρδιας ή απομακρυσμένη ΕΝΑΡΞΗ/ΛΗΞΗ)."""
        pending, self._pending = self._pending, None
        if not pending:
            return
        if result['errors']:
            QMessageBox.warning(self, 'Έλεγχος', '\n'.join(result['errors']))
            return
        description = pending['description']
        if result['warnings']:
            description += '\n\nΠΡΟΣΟΧΗ:\n- ' + '\n- '.join(result['warnings']) + '\n\nΝα συνεχίσω;'
        self.change(pending['action'], description=description, **pending['values'])

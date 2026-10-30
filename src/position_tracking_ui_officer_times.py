"""Officer window: shift start/end times, their later correction and the pre-change check."""
from datetime import datetime, timedelta
from PySide6.QtWidgets import QInputDialog, QMessageBox
from position_tracking_common import format_when
from position_tracking_personnel import PersonnelRepository


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

    def correct_end(self):
        """Διόρθωση ώρας ΕΝΑΡΞΗΣ ή ΛΗΞΗΣ εργασίας που έχει ήδη κλείσει (π.χ. η ΛΗΞΗ πατήθηκε αργά)."""
        if not self._state or self._future is not None or self._request:
            return
        found = PersonnelRepository.find(self._state['people'], self.target.text().strip())
        if len(found) != 1:
            QMessageBox.warning(self, 'Έλεγχος', 'Επιλέξτε έναν αστυνομικό της κεντρικής λίστας (ΑΓΜΣ ή επώνυμο και όνομα).')
            return
        self._closed_person = found[0]
        self.submit('sessions', self.endpoint.person_sessions, self.officer.text().strip(), found[0].agms)

    def after_sessions(self, sessions):
        """Συνέχεια μετά την ανάκτηση των ολοκληρωμένων εργασιών του ατόμου."""
        person = self._closed_person
        if not sessions:
            QMessageBox.warning(self, 'Διόρθωση εργασίας',
                                'Δεν βρέθηκε ολοκληρωμένη εργασία του ατόμου.\n'
                                'Αν η θέση είναι ακόμη ανοικτή, χρησιμοποιήστε ΑΠΟΜΑΚΡΥΣΜΕΝΗ ΛΗΞΗ.')
            return
        labels = [f"Θέση {s['position']} {s['direction']}:  {format_when(s['start_at'])} – {format_when(s['end_at'])}"
                  for s in sessions]
        label, ok = QInputDialog.getItem(self, 'Διόρθωση εργασίας',
                                         f'Ποια εργασία του {person.full_name} διορθώνεται;', labels, 0, False)
        if not ok:
            return
        chosen = sessions[labels.index(label)]
        which_label, ok = QInputDialog.getItem(self, 'Διόρθωση εργασίας', 'Ποια ώρα διορθώνεται;',
                                               ['Ώρα ΛΗΞΗΣ', 'Ώρα ΕΝΑΡΞΗΣ'], 0, False)
        if not ok:
            return
        is_end = which_label == 'Ώρα ΛΗΞΗΣ'
        started, ended = datetime.fromisoformat(chosen['start_at']), datetime.fromisoformat(chosen['end_at'])
        current = ended if is_end else started
        limit = dict(minimum=started.replace(second=0) + timedelta(minutes=1),
                     minimum_text='Η ΛΗΞΗ πρέπει να έπεται της ΕΝΑΡΞΗΣ (' + format_when(started) + ').') if is_end else {}
        answer = self._ask(self, 'Διόρθωση ' + which_label.lower(),
                           f"Νέα πραγματική {which_label.lower()} (τώρα {format_when(current)}):",
                           current.replace(second=0), reason=True, reason_label='Αιτιολογία μεταβολής', **limit)
        if not answer:
            return
        if not is_end and answer['moment'] >= ended:
            QMessageBox.warning(self, 'Έλεγχος', 'Η ΕΝΑΡΞΗ πρέπει να προηγείται της ΛΗΞΗΣ (' + format_when(ended) + ').')
            return
        action = 'CORRECT_END' if is_end else 'CORRECT_CLOSED_START'
        values = dict(agms=person.agms, position=chosen['position'], expected_start_id=chosen['start_event_id'],
                      expected_end_id=chosen['end_event_id'], expected_timestamp=current.isoformat(timespec='seconds'),
                      new_time=answer['moment'].isoformat(timespec='seconds'),
                      reason=answer['reason'], confirm_old=answer['confirm_old'])
        self._pending = dict(action=action, values=values,
            description=f"Διόρθωση ώρας {'ΛΗΞΗΣ' if is_end else 'ΕΝΑΡΞΗΣ'}\n{person.full_name} — ΑΓΜΣ {person.agms}\n"
                        f"Θέση {chosen['position']}\nΕΝΑΡΞΗ: {format_when(started)}\nΛΗΞΗ: {format_when(ended)}\n"
                        f"Νέα ώρα {'ΛΗΞΗΣ' if is_end else 'ΕΝΑΡΞΗΣ'}: {format_when(answer['moment'])}\n"
                        f"Αιτιολογία: {answer['reason']}")
        self.submit('check', self.endpoint.conflicts, self.officer.text().strip(), action, values)

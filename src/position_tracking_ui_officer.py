"""Central officer screen with declared AGMS and one owned network job."""
from datetime import datetime, timedelta
import hashlib
import json
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDateTimeEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit, QDialogButtonBox,
    QHeaderView, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QInputDialog)
from position_tracking_common import format_when, parse_day
from position_tracking_constants import CENTRAL_REVISION, CENTRAL_VERSION, STATISTICS_PIN_SHA256
from position_tracking_central import UNCONFIRMED
from position_tracking_officer import CentralOfficer, OfficerRequest, describe_history
from position_tracking_personnel import PersonnelRepository
from position_tracking_ui_map import BoothMapWidget
from position_tracking_ui_assets import ArrowComboBox
from position_tracking_ui_central_look import apply_look, build_header, new_card
from position_tracking_ui_officer_times import OfficerTimesMixin
from position_tracking_ui_when import ask_moment, from_qt, to_qt
from position_tracking_worker import SingleFlightWorker


def load_officer(app_dir, agms):
    endpoint = CentralOfficer.from_shared_directory(app_dir())
    return endpoint, endpoint.snapshot(agms)


def open_report(endpoint, agms, identifier, opener, personal=False):
    path = endpoint.personal_report(agms, identifier) if personal else endpoint.report(agms, identifier)
    opener(path)
    return str(path)


class CentralOfficerWindow(OfficerTimesMixin, QMainWindow):
    def __init__(self, services):
        super().__init__()
        self.services = services
        self.endpoint = None
        self._state = None
        self._request = None
        self._future = None
        self._worker = SingleFlightWorker('TDE-officer')
        self._closing = False
        self._pending = None
        self._refusal = ''
        self.setWindowTitle(f'Κεντρικό πάνελ ΑΞΥΠ v{CENTRAL_VERSION}{CENTRAL_REVISION}')
        self.resize(1180, 900)
        self.setMinimumSize(980, 700)
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(28, 22, 28, 20); outer.setSpacing(14)
        outer.addWidget(build_header(self, 'ΚΕΝΤΡΙΚΟ ΠΑΝΕΛ ΑΞΙΩΜΑΤΙΚΟΥ ΥΠΗΡΕΣΙΑΣ'))
        top = new_card(); layout = QVBoxLayout(top); layout.setContentsMargins(20, 14, 20, 14); layout.setSpacing(10)
        outer.addWidget(top)
        notice = QLabel('Απλή πρόσβαση. Το ΑΓΜΣ είναι δηλωμένο στοιχείο χειριστή, όχι πιστοποιημένη ταυτότητα.')
        notice.setObjectName('noticeBox'); notice.setWordWrap(True); layout.addWidget(notice)
        row = QHBoxLayout(); self.officer = QLineEdit(); self.officer.setPlaceholderText('ΑΓΜΣ ή επώνυμο ΑΞΥΠ')
        self.officer.setMinimumHeight(42)
        self.name = QLabel('—'); self.name.setObjectName('personName')
        self.refresh_btn = QPushButton('ΕΠΑΝΕΛΕΓΧΟΣ'); self.refresh_btn.setObjectName('metalPrimary'); self.refresh_btn.setMinimumHeight(42)
        row.addWidget(self.officer); row.addWidget(self.name, 1); row.addWidget(self.refresh_btn); layout.addLayout(row)
        self.officer.textChanged.connect(self._selection_changed)
        self.officer.editingFinished.connect(lambda: self.refresh() if self._state is None else None)
        self.refresh_btn.clicked.connect(self.refresh)
        self.info = QLabel('Συμπληρώστε το δηλωμένο ΑΓΜΣ ΑΞΥΠ και πατήστε ΕΠΑΝΕΛΕΓΧΟΣ.')
        self.info.setObjectName('infoBox'); self.info.setWordWrap(True); layout.addWidget(self.info)
        tabs = QTabWidget(); outer.addWidget(tabs, 1)
        self.actions = []
        shift_page = QWidget(); shift_layout = QVBoxLayout(shift_page); tabs.addTab(shift_page, 'Βάρδια / προσωπικό')
        self.shift_status = QLabel('—'); self.shift_status.setObjectName('statusBox'); self.shift_status.setAlignment(Qt.AlignCenter); shift_layout.addWidget(self.shift_status)
        row = QHBoxLayout(); shift_layout.addLayout(row)
        self.start_shift = self.button(row, 'ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ', self.begin_shift)
        self.end_shift = self.button(row, 'ΛΗΞΗ ΒΑΡΔΙΑΣ', self.end_current_shift)
        self.end_shift.setObjectName('endButton'); self.start_shift.setObjectName('startButton')
        self.import_btn = self.button(row, 'ΚΕΝΤΡΙΚΗ ΛΙΣΤΑ ΠΡΟΣΩΠΙΚΟΥ', self.import_people)
        self.members = self.table(['ΑΓΜΣ', 'Ονοματεπώνυμο', 'Συμμετοχή']); shift_layout.addWidget(self.members)
        row = QHBoxLayout(); shift_layout.addLayout(row)
        self.approve_btn = self.button(row, 'ΑΠΟΔΟΧΗ / ΑΝΑΙΡΕΣΗ ΕΞΑΙΡΕΣΗΣ', lambda: self.member('APPROVED'))
        self.exclude_btn = self.button(row, 'ΕΞΑΙΡΕΣΗ', lambda: self.member('EXCLUDED'))
        live_page = QWidget(); live_layout = QVBoxLayout(live_page); tabs.addTab(live_page, 'Πραγματικές θέσεις')
        self.active_table = self.table(['ΑΓΜΣ', 'Ονοματεπώνυμο', 'Θέση', 'Κατεύθυνση', 'ΕΝΑΡΞΗ'])
        live_layout.addWidget(self.active_table)
        form = QFormLayout(); live_layout.addLayout(form)
        self.target = QLineEdit(); self.position = ArrowComboBox(); self.position.addItems([str(i) for i in range(1, 15)])
        self.direction = ArrowComboBox(); self.direction.addItems(['ΕΙΣΟΔΟΣ', 'ΕΞΟΔΟΣ'])
        form.addRow('ΑΓΜΣ αστυνομικού', self.target); form.addRow('Θέση', self.position); form.addRow('Κατεύθυνση', self.direction)
        self.active_table.itemSelectionChanged.connect(self.select_active)
        row = QHBoxLayout(); live_layout.addLayout(row)
        self.remote_start = self.button(row, 'ΑΠΟΜΑΚΡΥΣΜΕΝΗ ΕΝΑΡΞΗ', lambda: self.physical('REMOTE_START'))
        self.remote_end = self.button(row, 'ΑΠΟΜΑΚΡΥΣΜΕΝΗ ΛΗΞΗ', lambda: self.physical('REMOTE_END'))
        self.correct_btn = self.button(row, 'ΔΙΟΡΘΩΣΗ ΩΡΑΣ ΕΝΑΡΞΗΣ', lambda: self.physical('CORRECT_START'))
        self.booths = BoothMapWidget(); tabs.addTab(self.booths, 'Σχέδιο γκισέ')
        reports_page = QWidget(); reports_layout = QVBoxLayout(reports_page); tabs.addTab(reports_page, 'Αναφορές / μηνύματα')
        self.reports = QComboBox(); reports_layout.addWidget(self.reports)
        row = QHBoxLayout(); reports_layout.addLayout(row)
        self.report_btn = self.button(row, 'ΑΝΑΦΟΡΑ ΕΡΓΑΣΙΑΣ', self.report)
        self.historical_btn = self.button(row, 'ΠΡΟΣΘΗΚΗ ΕΡΓΑΣΙΑΣ', self.historical)
        self.search_reports_btn = self.button(row, 'ΑΝΑΖΗΤΗΣΗ ΒΑΡΔΙΑΣ', self.search_reports)
        self.stats_btn = self.button(row, 'ΑΤΟΜΙΚΑ ΣΤΑΤΙΣΤΙΚΑ', self.statistics)
        self.history_btn = self.button(row, 'ΙΣΤΟΡΙΚΟ ΑΛΛΑΓΩΝ', self.history)
        self.shift_time_btn = self.button(row, 'ΔΙΟΡΘΩΣΗ ΩΡΑΣ ΒΑΡΔΙΑΣ', self.correct_shift_time)
        self.recipient = QComboBox(); reports_layout.addWidget(self.recipient)
        self.message = QPlainTextEdit(); self.message.setPlaceholderText('Υπηρεσιακό μήνυμα'); reports_layout.addWidget(self.message)
        row = QHBoxLayout(); reports_layout.addLayout(row)
        self.message_btn = self.button(row, 'ΑΠΟΣΤΟΛΗ ΜΗΝΥΜΑΤΟΣ', self.send_message)
        apply_look(self, root)
        self._timer = QTimer(self); self._timer.timeout.connect(self.poll); self._timer.start(100)
        self.buttons()

    @staticmethod
    def _ask(*args, **kwargs):
        """Single entry point of the time dialog (tests replace ask_moment here)."""
        return ask_moment(*args, **kwargs)

    def button(self, row, label, callback):
        button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        button.setObjectName('metalPrimary'); button.setMinimumHeight(44)
        self.actions.append(button)
        return button

    @staticmethod
    def table(columns):
        table = QTableWidget(0, len(columns)); table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QTableWidget.SelectRows); table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False); table.setAlternatingRowColors(True)
        return table

    def _selection_changed(self):
        self._state = None; self.name.setText('—'); self.buttons()

    def buttons(self):
        busy = self._future is not None
        ready = self._state is not None and not busy and self._request is None
        for button in self.actions:
            button.setEnabled(ready)
        self.officer.setEnabled(not busy and self._request is None)
        self.refresh_btn.setEnabled(not busy)
        if ready:
            shift = self._state['shift']
            self.start_shift.setEnabled(not shift); self.end_shift.setEnabled(bool(shift))
            self.approve_btn.setEnabled(bool(shift)); self.exclude_btn.setEnabled(bool(shift))

    def submit(self, kind, function, *args):
        if self._future is not None or self._closing:
            return
        self._kind = kind; self._started = time.monotonic()
        self._future = self._worker.submit(function, *args)
        self.info.setText('Αναμονή κεντρικής επιβεβαίωσης…'); self.buttons()

    def refresh(self):
        if self._future is not None or not self.officer.text().strip():
            return
        if self._request:
            self.submit('mutation', self.endpoint.check, self._request)
        else:
            self.submit('load', load_officer, self.services.app_dir, self.officer.text().strip())

    def poll(self):
        if self._closing or self._future is None:
            return
        if not self._future.done():
            if time.monotonic() - self._started > 3:
                self.info.setText(UNCONFIRMED + '\nΗ εργασία παραμένει σε εξέλιξη. Μην την επαναλάβετε.')
            return
        future, kind = self._future, self._kind; self._future = None
        try:
            result = future.result()
        except Exception as error:
            if kind == 'load':
                self._state = None
            if kind == 'check':
                self._pending = None
            self.info.setText(UNCONFIRMED + '\n' + str(error))
        else:
            if kind == 'load':
                self.endpoint, self._state = result; self.render()
            elif kind == 'mutation':
                self.info.setText(result.message)
                if result.status != 'UNKNOWN':
                    self._request = None
                    if result.status != 'CONFIRMED':
                        # The refresh below redraws the panel: keep the refusal visible.
                        self._refusal = 'ΔΕΝ ΕΓΙΝΕ Η ΚΑΤΑΧΩΡΗΣΗ.\n' + result.message
                        QMessageBox.warning(self, 'Η ενέργεια δεν έγινε', result.message)
                    self.refresh()
            elif kind == 'preview':
                data, count = result
                self.change('PERSONNEL_IMPORT', workbook=data, expected_revision=self._state['roster_revision'],
                            description=f'Ενημέρωση της κοινής λίστας με {count} άτομα;')
            elif kind == 'search_reports':
                self.reports.clear()
                self.reports.addItem('Επιλέξτε αναφορά', '')
                for shift in result:
                    self.reports.addItem(self.shift_label(shift), shift['shift_id'])
                self.info.setText('Βρέθηκαν αναφορές: ' + str(len(result)))
            elif kind == 'check':
                self.after_check(result)
            elif kind == 'history':
                dlg = QDialog(self); dlg.setWindowTitle('Κεντρικό ιστορικό δηλωμένων χειρισμών')
                lay = QVBoxLayout(dlg); text = QPlainTextEdit(); text.setReadOnly(True)
                text.setPlainText(describe_history(result)); lay.addWidget(text)
                dlg.resize(900, 650); dlg.exec(); dlg.deleteLater()
            else:
                self.info.setText('Δημιουργήθηκε η αναφορά: ' + str(result))
        self.buttons()

    @staticmethod
    def shift_label(shift):
        label = format_when(shift.get('start_at'))
        if shift.get('end_at'):
            label += ' – ' + format_when(shift['end_at'])
        return label

    def render(self):
        state = self._state
        self.name.setText(state['officer'].full_name + ' — δηλωμένος χειριστής')
        if self.officer.text().strip() != state['officer'].agms:
            # Typed by name: from here on every request carries the AGMS.
            self.officer.blockSignals(True); self.officer.setText(state['officer'].agms); self.officer.blockSignals(False)
        shift = state['shift']
        self.shift_status.setText('Βάρδια από ' + format_when(shift['start_at']) if shift else 'Δεν υπάρχει ενεργή βάρδια')
        self.members.setRowCount(len(state['people']))
        for row, person in enumerate(state['people']):
            status = next((label for key, label in [('approved','ΑΠΟΔΕΚΤΟΣ'),('excluded','ΕΞΑΙΡΕΣΗ'),('pending','ΑΝΑΜΟΝΗ')]
                           if shift and person.agms in shift.get(key, [])), 'ΕΚΤΟΣ')
            for col, value in enumerate([person.agms, person.full_name, status]):
                self.members.setItem(row, col, QTableWidgetItem(value))
        self.active_table.setRowCount(len(state['active']))
        for row, active in enumerate(state['active']):
            for col, key in enumerate(['agms','full_name','position','direction','timestamp']):
                self.active_table.setItem(row, col, QTableWidgetItem(format_when(active[key]) if key == 'timestamp' else active[key]))
        self.booths.set_active(state['active'])
        selected = self.reports.currentData()
        self.reports.clear(); self.reports.addItem('Τρέχουσα αναφορά', '')
        for shift in state['reports']:
            self.reports.addItem(self.shift_label(shift), shift['shift_id'])
        if selected:
            # Keep the chosen report after every refresh, so ΑΝΑΦΟΡΑ ΕΡΓΑΣΙΑΣ opens the
            # same shift the work was just added to.
            self.reports.setCurrentIndex(max(0, self.reports.findData(selected)))
        self.recipient.clear(); self.recipient.addItem('Όλοι οι ενεργοί σταθμοί', '')
        labels = state.get('station_labels', {})
        for client in state['clients']:
            self.recipient.addItem(labels.get(client['client_id']) or (client.get('computer', '') + ' / ' + client['client_id']),
                                   client['client_id'])
        refusal, self._refusal = self._refusal, ''
        self.info.setText(refusal or 'Κεντρικά δεδομένα επαληθεύτηκαν.')

    def change(self, action, description='', workbook=b'', **values):
        if not self._state or self._future is not None or self._request:
            return
        question = description or 'Να εφαρμοστεί η επιλεγμένη μεταβολή;'
        if QMessageBox.question(self, 'Επιβεβαίωση μεταβολής', question,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._request = OfficerRequest(action, self.officer.text().strip(), json.dumps(values), True, workbook=workbook)
        self.submit('mutation', self.endpoint.execute, self._request)

    def member(self, state):
        row = self.members.currentRow()
        if row >= 0 and self._state and self._state['shift']:
            self.change('MEMBER_STATE', agms=self.members.item(row,0).text(), state=state,
                        expected_shift_id=self._state['shift']['shift_id'],
                        description=('Αποδοχή / αναίρεση εξαίρεσης: ' if state == 'APPROVED' else 'Εξαίρεση: ')
                            + self.members.item(row,1).text() + ';\nΟι πραγματικές ώρες εργασίας δεν αλλάζουν.')

    def select_active(self):
        row = self.active_table.currentRow()
        if row >= 0 and self.active_table.item(row,0):
            self.target.setText(self.active_table.item(row,0).text())

    def physical(self, action):
        if not self._state:
            return
        agms = self.target.text().strip()
        found = PersonnelRepository.find(self._state['people'], agms)
        person = found[0] if len(found) == 1 else None
        if not person:
            QMessageBox.warning(self, 'Έλεγχος', 'Επιλέξτε έναν αστυνομικό της κεντρικής λίστας (ΑΓΜΣ ή επώνυμο και όνομα).'); return
        agms = person.agms
        active = next((a for a in self._state['active'] if a['agms'] == agms), None)
        values = dict(agms=agms)
        if action == 'REMOTE_START':
            values.update(position=self.position.currentText(), direction=self.direction.currentText())
            if active:
                QMessageBox.warning(self, 'Έλεγχος', 'Ο αστυνομικός έχει ήδη ανοικτή θέση. Πρώτα ΛΗΞΗ.'); return
        elif not active:
            QMessageBox.warning(self, 'Έλεγχος', 'Δεν υπάρχει επιβεβαιωμένη ενεργή θέση.'); return
        else:
            values['expected_start_id'] = active['event_id']
            if action == 'CORRECT_START':
                values['expected_timestamp'] = active['timestamp']
        now = datetime.now().replace(second=0, microsecond=0)
        if action == 'CORRECT_START':
            started = datetime.fromisoformat(active['timestamp'])
            title, prompt, default, key = ('Πραγματική ώρα ΕΝΑΡΞΗΣ',
                f"Νέα πραγματική ώρα ΕΝΑΡΞΗΣ (τώρα {format_when(started)}, ίδια ημερομηνία):", started.replace(second=0), 'new_time')
            minimum, minimum_text = None, ''
        elif action == 'REMOTE_END':
            started = datetime.fromisoformat(active['timestamp'])
            title, prompt, default, key = ('Ώρα ΛΗΞΗΣ',
                f"Πραγματική ώρα ΛΗΞΗΣ (η ΕΝΑΡΞΗ ήταν {format_when(started)}):", now, 'when')
            minimum, minimum_text = started.replace(second=0), 'Η ΛΗΞΗ προηγείται της ΕΝΑΡΞΗΣ (' + format_when(started) + ').'
        else:
            title, prompt, default, key = ('Ώρα ΕΝΑΡΞΗΣ',
                f"Πραγματική ώρα ΕΝΑΡΞΗΣ για {person.full_name} (προτείνεται η τρέχουσα):", now, 'when')
            minimum, minimum_text = None, ''
        answer = ask_moment(self, title, prompt, default, reason=True, reason_label='Αιτιολογία μεταβολής',
                            minimum=minimum, minimum_text=minimum_text)
        if not answer:
            return
        moment = answer['moment']
        if action == 'CORRECT_START' and moment.date() != started.date():
            QMessageBox.warning(self, 'Έλεγχος', 'Η διόρθωση περιορίζεται στην ίδια ημερομηνία.'); return
        values[key] = moment.isoformat(timespec='seconds')
        values.update(reason=answer['reason'], confirm_old=answer['confirm_old'])
        label = {'REMOTE_START': 'Απομακρυσμένη ΕΝΑΡΞΗ', 'REMOTE_END': 'Απομακρυσμένη ΛΗΞΗ',
                 'CORRECT_START': 'Διόρθωση ώρας ΕΝΑΡΞΗΣ'}[action]
        previous = format_when(active['timestamp']) if active else 'Χωρίς ανοικτή καταχώριση'
        place = active['position'] if active else values['position']
        description = (f'{label}\n{person.full_name} — ΑΓΜΣ {agms}\nΘέση {place}\n'
                       f'Προηγούμενη ώρα: {previous}\nΝέα ώρα: {format_when(moment)}\nΑιτιολογία: {answer["reason"]}')
        self._pending = dict(action=action, values=values, description=description)
        self.submit('check', self.endpoint.conflicts, self.officer.text().strip(), action, values)

    def import_people(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Κεντρική ενημέρωση προσωπικού', '', 'Excel (*.xlsx *.xlsm)')
        if path:
            self.submit('preview', self.endpoint.preview_personnel, path)

    def history_values(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Ολοκληρωμένη ιστορική εργασία')
        form = QFormLayout(dialog)
        agms = QLineEdit(self.target.text().strip())
        agms.setPlaceholderText('ΑΓΜΣ ή επώνυμο και όνομα')
        who = QLabel(''); who.setWordWrap(True)
        matches = []

        def lookup():
            matches[:] = PersonnelRepository.find(self._state['people'], agms.text().strip()) if agms.text().strip() else []
            who.setText(f'{matches[0].full_name} — ΑΓΜΣ {matches[0].agms}' if len(matches) == 1
                        else 'Πολλοί με αυτό το όνομα: γράψτε επώνυμο και όνομα ή το ΑΓΜΣ.' if matches
                        else 'Δεν βρέθηκε στην κεντρική λίστα.' if agms.text().strip() else '')
        agms.textChanged.connect(lookup); lookup()
        booth = QComboBox(); booth.addItems([str(i) for i in range(1,15)])
        way = QComboBox(); way.addItems(['ΕΙΣΟΔΟΣ','ΕΞΟΔΟΣ'])
        now = datetime.now().replace(second=0, microsecond=0)
        started = QDateTimeEdit(to_qt(now)); ended = QDateTimeEdit(to_qt(now))
        for editor in (started, ended):
            editor.setDisplayFormat('dd/MM/yyyy HH:mm'); editor.setCalendarPopup(True)
        reason = QPlainTextEdit(); reason.setMaximumHeight(75)
        for title, widget in [('ΑΓΜΣ / όνομα',agms),('Άτομο',who),('Θέση',booth),('Κατεύθυνση',way),
                              ('ΕΝΑΡΞΗ',started),('ΛΗΞΗ',ended),('Αιτιολογία',reason)]:
            form.addRow(title,widget)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        def accept():
            if len(matches) != 1:
                QMessageBox.warning(dialog, 'Έλεγχος', 'Επιλέξτε έναν αστυνομικό της κεντρικής λίστας (ΑΓΜΣ ή επώνυμο και όνομα).')
            else:
                dialog.accept()
        buttons.accepted.connect(accept); buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            dialog.deleteLater()
            return None
        values = dict(agms=matches[0].agms,position=booth.currentText(),
                      direction=way.currentText(),reason=reason.toPlainText().strip(),
                      start_at=from_qt(started.dateTime()),end_at=from_qt(ended.dateTime()))
        dialog.deleteLater()
        return values

    def historical(self):
        if not self._state or self._future is not None or self._request:
            return
        identifier = self.reports.currentData() or (self._state.get('shift') or {}).get('shift_id')
        if not identifier:
            QMessageBox.warning(self, 'Αναφορά', 'Επιλέξτε αναφορά βάρδιας.')
            return
        values = self.history_values()
        if values is None:
            return
        person_name = next((p.full_name for p in self._state['people'] if p.agms == values['agms']), values['agms'])
        start, end = values['start_at'], values['end_at']
        if end <= start or end > datetime.now() + timedelta(minutes=2):
            QMessageBox.warning(self, 'Έλεγχος', 'Ελέγξτε τις πραγματικές ημερομηνίες και ώρες.')
            return
        values.update(shift_id=str(identifier),start_at=start.isoformat(timespec='seconds'),
                      end_at=end.isoformat(timespec='seconds'))
        shift = self._state.get('shift') or {}
        label = self.reports.currentText() if self.reports.currentData() else (
            'τρέχουσα βάρδια από ' + format_when(shift.get('start_at')))
        self.change('HISTORICAL_ADD',
                    description=f'Προσθήκη ολοκληρωμένης εργασίας\nΆτομο: {person_name}\n'
                                f'Θέση {values["position"]} — {values["direction"]}\n'
                                f'Από {format_when(start)} έως {format_when(end)}\n'
                                f'Στην αναφορά βάρδιας: {label}',
                    **values)

    def search_reports(self):
        day, ok = QInputDialog.getText(self, 'Αναζήτηση βάρδιας',
                                        'Ημερομηνία έναρξης βάρδιας (ΗΗ/ΜΜ/ΕΕΕΕ)')
        if not ok:
            return
        try:
            value = parse_day(day).isoformat()
        except ValueError:
            QMessageBox.warning(self, 'Έλεγχος', 'Μη έγκυρη ημερομηνία.')
            return
        self.submit('search_reports', self.endpoint.find_reports,
                    self.officer.text().strip(), value)

    def report(self):
        self.submit('report', open_report, self.endpoint, self.officer.text().strip(), self.reports.currentData() or '', self.services.open_path)

    def statistics(self):
        pin, ok = QInputDialog.getText(self, 'Ατομικά στατιστικά', 'Κωδικός πρόσβασης', QLineEdit.Password)
        if not ok: return
        if hashlib.sha256(pin.strip().encode()).hexdigest() != STATISTICS_PIN_SHA256:
            QMessageBox.warning(self, 'Στατιστικά', 'Λανθασμένος κωδικός.'); return
        self.submit('report', open_report, self.endpoint, self.officer.text().strip(), self.target.text().strip(), self.services.open_path, True)

    def history(self):
        self.submit('history', self.endpoint.history, self.officer.text().strip())

    def send_message(self):
        targets = [self.recipient.currentData()] if self.recipient.currentData() else [c['client_id'] for c in self._state['clients']]
        self.change('MESSAGE', targets=targets, text=self.message.toPlainText(),
                    description=f'Αποστολή σε {len(targets)} σταθμούς;\n' + self.message.toPlainText())

    def shutdown(self):
        self._closing = True; self._timer.stop(); self._worker.close()

    def closeEvent(self, event):
        if self._future is not None or self._request:
            if QMessageBox.question(self, 'Εκκρεμής ενέργεια', 'Η ενέργεια μπορεί να παραμένει σε εξέλιξη. Κλείσιμο και επανέλεγχος στην επόμενη εκκίνηση;',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                event.ignore(); return
        self.shutdown(); event.accept()

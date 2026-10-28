"""Central officer screen with declared AGMS and one owned network job."""
from datetime import datetime
import hashlib
import json
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QInputDialog)
from position_tracking_constants import STATISTICS_PIN_SHA256
from position_tracking_central import UNCONFIRMED
from position_tracking_officer import CentralOfficer, OfficerRequest
from position_tracking_ui_map import BoothMapWidget
from position_tracking_worker import SingleFlightWorker


def load_officer(app_dir, agms):
    endpoint = CentralOfficer.from_shared_directory(app_dir())
    return endpoint, endpoint.snapshot(agms)


def open_report(endpoint, agms, identifier, opener, personal=False):
    path = endpoint.personal_report(agms, identifier) if personal else endpoint.report(agms, identifier)
    opener(path)
    return str(path)


class CentralOfficerWindow(QMainWindow):
    def __init__(self, services):
        super().__init__()
        self.services = services
        self.endpoint = None
        self._state = None
        self._request = None
        self._future = None
        self._worker = SingleFlightWorker('TDE-officer')
        self._closing = False
        self.setWindowTitle('Κεντρικό πάνελ ΑΞΥΠ — δοκιμαστική λειτουργία')
        self.resize(1120, 850)
        root = QWidget(); self.setCentralWidget(root); layout = QVBoxLayout(root)
        notice = QLabel('Απλή πρόσβαση. Το ΑΓΜΣ είναι δηλωμένο στοιχείο χειριστή, όχι πιστοποιημένη ταυτότητα.')
        notice.setWordWrap(True); layout.addWidget(notice)
        row = QHBoxLayout(); self.officer = QLineEdit(); self.officer.setPlaceholderText('ΑΓΜΣ ΑΞΥΠ')
        self.name = QLabel('—'); self.refresh_btn = QPushButton('ΕΠΑΝΕΛΕΓΧΟΣ')
        row.addWidget(self.officer); row.addWidget(self.name, 1); row.addWidget(self.refresh_btn); layout.addLayout(row)
        self.officer.textChanged.connect(self._selection_changed)
        self.officer.editingFinished.connect(lambda: self.refresh() if self._state is None else None)
        self.refresh_btn.clicked.connect(self.refresh)
        self.info = QLabel('Συμπληρώστε το δηλωμένο ΑΓΜΣ ΑΞΥΠ και πατήστε ΕΠΑΝΕΛΕΓΧΟΣ.')
        self.info.setWordWrap(True); layout.addWidget(self.info)
        tabs = QTabWidget(); layout.addWidget(tabs, 1)
        self.actions = []
        shift_page = QWidget(); shift_layout = QVBoxLayout(shift_page); tabs.addTab(shift_page, 'Βάρδια / προσωπικό')
        self.shift_status = QLabel('—'); shift_layout.addWidget(self.shift_status)
        row = QHBoxLayout(); shift_layout.addLayout(row)
        self.start_shift = self.button(row, 'ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ', lambda: self.change('SHIFT_START',
            description='Να ξεκινήσει νέα βάρδια; Οι πραγματικές θέσεις δεν θα μεταβληθούν.'))
        self.end_shift = self.button(row, 'ΛΗΞΗ ΒΑΡΔΙΑΣ', self.end_current_shift)
        self.import_btn = self.button(row, 'ΚΕΝΤΡΙΚΗ ΛΙΣΤΑ ΠΡΟΣΩΠΙΚΟΥ', self.import_people)
        self.members = self.table(['ΑΓΜΣ', 'Ονοματεπώνυμο', 'Συμμετοχή']); shift_layout.addWidget(self.members)
        row = QHBoxLayout(); shift_layout.addLayout(row)
        self.approve_btn = self.button(row, 'ΑΠΟΔΟΧΗ / ΑΝΑΙΡΕΣΗ ΕΞΑΙΡΕΣΗΣ', lambda: self.member('APPROVED'))
        self.exclude_btn = self.button(row, 'ΕΞΑΙΡΕΣΗ', lambda: self.member('EXCLUDED'))
        live_page = QWidget(); live_layout = QVBoxLayout(live_page); tabs.addTab(live_page, 'Πραγματικές θέσεις')
        self.active_table = self.table(['ΑΓΜΣ', 'Ονοματεπώνυμο', 'Θέση', 'Κατεύθυνση', 'ΕΝΑΡΞΗ'])
        live_layout.addWidget(self.active_table)
        form = QFormLayout(); live_layout.addLayout(form)
        self.target = QLineEdit(); self.position = QComboBox(); self.position.addItems([str(i) for i in range(1, 15)])
        self.direction = QComboBox(); self.direction.addItems(['ΕΙΣΟΔΟΣ', 'ΕΞΟΔΟΣ'])
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
        self.stats_btn = self.button(row, 'ΑΤΟΜΙΚΑ ΣΤΑΤΙΣΤΙΚΑ', self.statistics)
        self.history_btn = self.button(row, 'ΙΣΤΟΡΙΚΟ ΑΛΛΑΓΩΝ', self.history)
        self.recipient = QComboBox(); reports_layout.addWidget(self.recipient)
        self.message = QPlainTextEdit(); self.message.setPlaceholderText('Υπηρεσιακό μήνυμα'); reports_layout.addWidget(self.message)
        row = QHBoxLayout(); reports_layout.addLayout(row)
        self.message_btn = self.button(row, 'ΑΠΟΣΤΟΛΗ ΜΗΝΥΜΑΤΟΣ', self.send_message)
        self._timer = QTimer(self); self._timer.timeout.connect(self.poll); self._timer.start(100)
        self.buttons()

    def button(self, row, label, callback):
        button = QPushButton(label); button.clicked.connect(callback); row.addWidget(button)
        self.actions.append(button)
        return button

    @staticmethod
    def table(columns):
        table = QTableWidget(0, len(columns)); table.setHorizontalHeaderLabels(columns)
        table.setSelectionBehavior(QTableWidget.SelectRows); table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
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
            self.info.setText(UNCONFIRMED + '\n' + str(error))
        else:
            if kind == 'load':
                self.endpoint, self._state = result; self.render()
            elif kind == 'mutation':
                self.info.setText(result.message)
                if result.status != 'UNKNOWN':
                    self._request = None; self.refresh()
            elif kind == 'preview':
                data, count = result
                self.change('PERSONNEL_IMPORT', workbook=data, expected_revision=self._state['roster_revision'],
                            description=f'Ενημέρωση της κοινής λίστας με {count} άτομα;')
            elif kind == 'history':
                dlg = QDialog(self); dlg.setWindowTitle('Κεντρικό ιστορικό δηλωμένων χειρισμών')
                lay = QVBoxLayout(dlg); text = QPlainTextEdit(); text.setReadOnly(True)
                text.setPlainText(json.dumps(result, ensure_ascii=False, indent=2)); lay.addWidget(text)
                dlg.resize(900, 650); dlg.exec(); dlg.deleteLater()
            else:
                self.info.setText('Δημιουργήθηκε η αναφορά: ' + str(result))
        self.buttons()

    def render(self):
        state = self._state
        self.name.setText(state['officer'].full_name + ' — δηλωμένος χειριστής')
        shift = state['shift']
        self.shift_status.setText('Βάρδια: ' + (shift['start_at'] if shift else 'Δεν υπάρχει ενεργή βάρδια'))
        self.members.setRowCount(len(state['people']))
        for row, person in enumerate(state['people']):
            status = next((label for key, label in [('approved','ΑΠΟΔΕΚΤΟΣ'),('excluded','ΕΞΑΙΡΕΣΗ'),('pending','ΑΝΑΜΟΝΗ')]
                           if shift and person.agms in shift.get(key, [])), 'ΕΚΤΟΣ')
            for col, value in enumerate([person.agms, person.full_name, status]):
                self.members.setItem(row, col, QTableWidgetItem(value))
        self.active_table.setRowCount(len(state['active']))
        for row, active in enumerate(state['active']):
            for col, key in enumerate(['agms','full_name','position','direction','timestamp']):
                self.active_table.setItem(row, col, QTableWidgetItem(active[key]))
        self.booths.set_active(state['active'])
        self.reports.clear(); self.reports.addItem('Τρέχουσα αναφορά', '')
        for shift in state['reports']:
            self.reports.addItem(shift['start_at'], shift['shift_id'])
        self.recipient.clear(); self.recipient.addItem('Όλοι οι ενεργοί σταθμοί', '')
        for client in state['clients']:
            self.recipient.addItem(client.get('computer', '') + ' / ' + client['client_id'], client['client_id'])
        self.info.setText('Κεντρικά δεδομένα επαληθεύτηκαν.')

    def change(self, action, description='', workbook=b'', **values):
        if not self._state or self._future is not None or self._request:
            return
        question = description or 'Να εφαρμοστεί η επιλεγμένη μεταβολή;'
        if QMessageBox.question(self, 'Επιβεβαίωση μεταβολής', question,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self._request = OfficerRequest(action, self.officer.text().strip(), json.dumps(values), True, workbook=workbook)
        self.submit('mutation', self.endpoint.execute, self._request)

    def end_current_shift(self):
        if self._state and self._state['shift']:
            self.change('SHIFT_END', expected_shift_id=self._state['shift']['shift_id'],
                description='Να ολοκληρωθεί η βάρδια; Οι φυσικές θέσεις παραμένουν ενεργές.')

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
        person = next((p for p in self._state['people'] if p.agms == agms), None)
        if not person:
            QMessageBox.warning(self, 'Έλεγχος', 'Επιλέξτε αστυνομικό της κεντρικής λίστας.'); return
        active = next((a for a in self._state['active'] if a['agms'] == agms), None)
        values = dict(agms=agms, when=datetime.now().isoformat(timespec='seconds'))
        if action == 'REMOTE_START':
            values.update(position=self.position.currentText(), direction=self.direction.currentText())
        elif not active:
            QMessageBox.warning(self, 'Έλεγχος', 'Δεν υπάρχει επιβεβαιωμένη ενεργή θέση.'); return
        else:
            values['expected_start_id'] = active['event_id']
        if action == 'CORRECT_START':
            value, ok = QInputDialog.getText(self, 'Πραγματική ώρα', 'Νέα ημερομηνία και ώρα (YYYY-MM-DD HH:MM:SS)',
                                            text=active['timestamp'].replace('T',' '))
            if not ok: return
            try: values['new_time'] = datetime.fromisoformat(value).isoformat(timespec='seconds')
            except ValueError:
                QMessageBox.warning(self, 'Έλεγχος', 'Μη έγκυρη ημερομηνία και ώρα.'); return
            values['expected_timestamp'] = active['timestamp']
        reason, ok = QInputDialog.getText(self, 'Αιτιολογία', 'Αιτιολογία μεταβολής')
        if not ok: return
        if len(reason.strip()) < 5:
            QMessageBox.warning(self, 'Έλεγχος', 'Η αιτιολογία απαιτεί τουλάχιστον 5 χαρακτήρες.'); return
        values['reason'] = reason.strip()
        label = {'REMOTE_START': 'Απομακρυσμένη ΕΝΑΡΞΗ', 'REMOTE_END': 'Απομακρυσμένη ΛΗΞΗ',
                 'CORRECT_START': 'Διόρθωση ώρας ΕΝΑΡΞΗΣ'}[action]
        previous = active['timestamp'] if active else 'Χωρίς ανοικτή καταχώριση'
        place = active['position'] if active else values['position']
        self.change(action, description=f'{label}\n{person.full_name} — ΑΓΜΣ {agms}\nΘέση {place}\n'
            f'Προηγούμενη ώρα: {previous}\nΝέα ώρα: {values.get("new_time", values["when"])}\nΑιτιολογία: {reason}', **values)

    def import_people(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Κεντρική ενημέρωση προσωπικού', '', 'Excel (*.xlsx *.xlsm)')
        if path:
            self.submit('preview', self.endpoint.preview_personnel, path)

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

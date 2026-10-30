"""Central operator screen; every shared-file operation runs in a worker."""
import time
import uuid
from dataclasses import replace
from datetime import datetime
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QComboBox, QFormLayout, QHBoxLayout, QLabel,
                              QLineEdit, QMainWindow, QMessageBox, QPushButton,
                              QVBoxLayout, QWidget)

from position_tracking_central import CentralOperator, PositionRequest, UNCONFIRMED
from position_tracking_common import format_when
from position_tracking_constants import CENTRAL_REVISION, CENTRAL_VERSION
from position_tracking_ui_assets import ArrowComboBox
from position_tracking_ui_central_look import apply_look, build_header, new_card
from position_tracking_worker import SingleFlightWorker


def _load_selection(endpoint, app_directory, agms):
    # Workers must not own a bound QWidget method: its last reference could be
    # released on that thread after QApplication/window teardown (Qt 6.12 crash).
    endpoint = endpoint or CentralOperator.from_shared_directory(app_directory())
    return endpoint, endpoint.lookup(agms)


# A lookup starts only after the operator pauses typing. Every lookup touches
# the shared folder, so one lookup per keystroke from 15 stations is needless load.
LOOKUP_PAUSE_SECONDS = 0.35
# A shared-folder read cannot be cancelled. After this long the window stops
# waiting for it, ignores its late result and lets the operator recheck with a
# fresh worker. START/END commands are never abandoned this way.
READ_ABANDON_SECONDS = 8
MAX_ABANDONED_READS = 3


class CentralOperatorWindow(QMainWindow):
    def __init__(self, services):
        super().__init__()
        self.services = services
        self.endpoint = None
        self._read_worker = SingleFlightWorker("TDE-central-read")
        self._action_worker = SingleFlightWorker("TDE-central-action")
        self._read_future = None
        self._action_future = None
        self._request = None
        self._active = None
        self._person = None
        self._dirty = True
        self._lookup_not_before = 0.0
        self._abandoned_reads = 0
        self._closing = False
        self._client_id = uuid.uuid4().hex
        self._mail_worker = SingleFlightWorker('TDE-central-mail')
        self._mail_future = None
        self._mail_messages = []
        self.setWindowTitle(f"Καταγραφή Θέσεων v{CENTRAL_VERSION}{CENTRAL_REVISION} — κεντρική λειτουργία")
        self.resize(900, 760)
        self.setMinimumSize(760, 640)
        root = QWidget(self)
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(28, 22, 28, 20)
        outer.setSpacing(14)
        outer.addWidget(build_header(self))
        card = new_card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        outer.addWidget(card, 1)
        title = QLabel("ΠΡΟΣΩΠΙΚΟ")
        title.setObjectName("cardTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(12)
        self.agms_input = QLineEdit()
        self.agms_input.setMinimumHeight(42)
        self.agms_input.setPlaceholderText("Α.Γ.Μ.Σ. ή επώνυμο")
        self.agms_input.textChanged.connect(self._selection_changed)
        self.person_name = QLabel("—")
        self.person_name.setObjectName("personName")
        self.person_name.setWordWrap(True)
        self.direction = ArrowComboBox()
        self.direction.addItems(["ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"])
        self.position = ArrowComboBox()
        self.position.addItems([str(i) for i in range(1, 15)])
        for combo in (self.direction, self.position):
            combo.setMinimumHeight(42)
        for label, widget in (("Α.Γ.Μ.Σ.", self.agms_input), ("Αστυνομικός", self.person_name),
                              ("ΚΑΤΕΥΘΥΝΣΗ", self.direction), ("ΘΕΣΗ", self.position)):
            form.addRow(label, widget)
        layout.addLayout(form)
        self.active_status = QLabel("ΕΛΕΓΧΟΣ ΚΕΝΤΡΙΚΩΝ ΔΕΔΟΜΕΝΩΝ…")
        self.active_status.setObjectName("statusBox")
        self.active_status.setAlignment(Qt.AlignCenter)
        self.active_status.setWordWrap(True)
        layout.addWidget(self.active_status)
        layout.addStretch()
        row = QHBoxLayout()
        row.setSpacing(12)
        self.start_btn = QPushButton("ΕΝΑΡΞΗ")
        self.start_btn.setObjectName("startButton")
        self.end_btn = QPushButton("ΛΗΞΗ")
        self.end_btn.setObjectName("endButton")
        self.start_btn.clicked.connect(lambda: self._act("START"))
        self.end_btn.clicked.connect(lambda: self._act("END"))
        for button in (self.start_btn, self.end_btn):
            button.setMinimumHeight(54)
            button.setEnabled(False)
            row.addWidget(button)
        layout.addLayout(row)
        self.recheck_btn = QPushButton("ΕΠΑΝΕΛΕΓΧΟΣ ΚΕΝΤΡΙΚΩΝ ΔΕΔΟΜΕΝΩΝ")
        self.recheck_btn.setObjectName("metalPrimary")
        self.recheck_btn.setMinimumHeight(44)
        self.recheck_btn.clicked.connect(self._recheck)
        layout.addWidget(self.recheck_btn)
        self.info = QLabel("")
        self.info.setObjectName("infoBox")
        self.info.setAlignment(Qt.AlignCenter)
        self.info.setWordWrap(True)
        outer.addWidget(self.info)
        self.service_message = QLabel(''); self.service_message.setWordWrap(True)
        self.service_message.setObjectName("infoBox"); self.service_message.setVisible(False)
        self.ack_message = QPushButton('ΕΛΑΒΑ ΓΝΩΣΗ ΥΠΗΡΕΣΙΑΚΟΥ ΜΗΝΥΜΑΤΟΣ')
        self.ack_message.setObjectName("metalPrimary")
        self.ack_message.setVisible(False); self.ack_message.clicked.connect(self._ack_message)
        outer.addWidget(self.service_message); outer.addWidget(self.ack_message)
        self.exit_btn = QPushButton("ΕΞΟΔΟΣ ΑΠΟ ΤΟ ΠΡΟΓΡΑΜΜΑ")
        self.exit_btn.setObjectName("exitButton")
        self.exit_btn.setMinimumHeight(44)
        self.exit_btn.clicked.connect(self.close)
        outer.addWidget(self.exit_btn)
        apply_look(self, root)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(100)
        self._mail_timer = QTimer(self); self._mail_timer.timeout.connect(self._poll_mail); self._mail_timer.start(10000)
        self._poll()

    def _poll_mail(self):
        if self._closing or self.endpoint is None:
            return
        if self._mail_future is None:
            self._mail_future = self._mail_worker.submit(self.endpoint.communication, self._client_id)

    def _finish_mail(self):
        if self._mail_future is not None:
            if not self._mail_future.done():
                return
            try:
                self._mail_messages = self._mail_future.result()
            except Exception:
                self.service_message.setText('Δεν επιβεβαιώθηκε ο έλεγχος υπηρεσιακών μηνυμάτων.')
                self.service_message.setVisible(True)
            else:
                message = self._mail_messages[0] if self._mail_messages else None
                self.service_message.setText(message['text'] if message else '')
                self.service_message.setVisible(bool(message))
                self.ack_message.setVisible(bool(message))
            self._mail_future = None

    def _ack_message(self):
        if self._mail_future is not None or not self._mail_messages:
            return
        self._mail_future = self._mail_worker.submit(self.endpoint.communication, self._client_id,
                                                   self._mail_messages[0]['message_id'])
        self.ack_message.setVisible(False)

    def _selection_changed(self):
        self._dirty = True
        self._lookup_not_before = time.monotonic() + LOOKUP_PAUSE_SECONDS
        self._person = None
        self._active = None
        self.person_name.setText("—")
        self._buttons()

    def _buttons(self):
        busy = self._request is not None or self._action_future is not None
        ready = self._person is not None and not busy and not self._dirty
        self.start_btn.setEnabled(ready and self._active is None)
        self.end_btn.setEnabled(ready and self._active is not None)
        # Repeated clicks never submit another job behind blocked SMB work.
        self.recheck_btn.setEnabled(self._read_future is None and self._action_future is None
                                    and self._abandoned_reads < MAX_ABANDONED_READS)

    def _poll(self):
        if self._closing:
            return
        self._finish_mail()
        if self._action_future is not None:
            if not self._action_future.done():
                if time.monotonic() - self._action_started > 3:
                    self.info.setText(UNCONFIRMED + "\nΗ εντολή παραμένει σε εξέλιξη. Μην την επαναλάβετε.")
                self._buttons()
                return
            future = self._action_future
            self._action_future = None
            try:
                outcome = future.result()
            except Exception:
                self.info.setText(UNCONFIRMED + "\nΠατήστε ΕΠΑΝΕΛΕΓΧΟΣ όταν αποκατασταθεί η πρόσβαση.")
            else:
                self.info.setText(outcome.message)
                if outcome.status == 'HANDOVER_REQUIRED':
                    self._confirm_handover(outcome.event)
                    self._buttons()
                    return
                if outcome.status != "UNKNOWN":
                    self._request = None
                    self._dirty = True
        if self._read_future is not None:
            if not self._read_future.done():
                waited = time.monotonic() - self._read_started
                if waited > 3 and self._request is None:
                    self.active_status.setText(UNCONFIRMED)
                if waited > READ_ABANDON_SECONDS and self._request is None:
                    self._abandon_read()
                self._buttons()
                return
            future = self._read_future
            self._read_future = None
            current = self._read_agms == self.agms_input.text().strip()
            try:
                endpoint, (person, active) = future.result()
            except Exception as error:
                if current and self._request is None:
                    self.active_status.setText(UNCONFIRMED)
                    # The real reason, so a missing list is told apart from a bad file.
                    self.info.setText("Αιτία: " + (str(error) or type(error).__name__))
                    self._person = None
                    self._active = None
                    self._dirty = False  # Explicit recheck; no network polling.
            else:
                self.endpoint = endpoint
                if current and self._request is None:
                    self._person, self._active = person, active
                    self._dirty = False
                    if self.info.text().startswith("Αιτία:"):
                        self.info.setText("")
                    self.person_name.setText(person.display if person else "—")
                    if active:
                        self.active_status.setText(
                            f"ΕΝΕΡΓΗ: ΘΕΣΗ {active['position']} — {active['direction']} — από {format_when(active['timestamp'])}")
                    else:
                        many = getattr(endpoint, "ambiguous", ())
                        if person:
                            self.active_status.setText("Δεν υπάρχει ανοικτή καταχώριση")
                        elif many:
                            self.active_status.setText("Βρέθηκαν πολλοί: " + " | ".join(p.display for p in many)
                                                       + "\nΓράψτε επώνυμο και όνομα ή το ΑΓΜΣ.")
                        else:
                            self.active_status.setText("Δεν βρέθηκε. Γράψτε Α.Γ.Μ.Σ. ή επώνυμο.")
        # After MAX_ABANDONED_READS the read worker is closed for good: submitting
        # to it would raise in this 100 ms timer slot on every tick.
        if (self._dirty and self._read_future is None and self._request is None
                and self._abandoned_reads < MAX_ABANDONED_READS
                and time.monotonic() >= self._lookup_not_before):
            self._read_agms = self.agms_input.text().strip()
            self._read_started = time.monotonic()
            self._read_future = self._read_worker.submit(
                _load_selection, self.endpoint, self.services.app_dir, self._read_agms)
        self._buttons()

    def _abandon_read(self):
        """Stop waiting for a hung shared-folder read; never touch a START/END."""
        self._read_future = None
        self._abandoned_reads += 1
        self._person = None
        self._active = None
        self._dirty = False  # Explicit recheck only; no automatic retry storm.
        self._read_worker.close()
        if self._abandoned_reads >= MAX_ABANDONED_READS:
            self.info.setText(UNCONFIRMED + "\nΟ κοινός φάκελος δεν ανταποκρίνεται. "
                              "Κλείστε και ανοίξτε ξανά το πρόγραμμα.")
        else:
            self._read_worker = SingleFlightWorker("TDE-central-read")
            self.info.setText(UNCONFIRMED + "\nΠατήστε ΕΠΑΝΕΛΕΓΧΟΣ για νέα προσπάθεια.")
            self.active_status.setText(UNCONFIRMED)

    def _confirm_handover(self, previous):
        answer = QMessageBox.question(self, 'Αντικατάσταση αστυνομικού',
            f"Η ΘΕΣΗ {previous['position']} — {previous['direction']} είναι κατειλημμένη από "
            f"{previous.get('full_name') or previous['agms']} (ΑΓΜΣ {previous['agms']}).\n\n"
            f"Νέα καταχώριση: ΑΓΜΣ {self._request.agms} — {self._request.direction}.\n\n"
            f"Να γίνει ΛΗΞΗ του προηγούμενου και ΕΝΑΡΞΗ του νέου στην ίδια χρονική στιγμή;",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self._request = replace(self._request, handover_start_id=previous['event_id'], when=datetime.now())
            self._action_started = time.monotonic()
            self._action_future = self._action_worker.submit(self.endpoint.execute, self._request)
            self.info.setText('ΑΝΑΜΟΝΗ ΚΕΝΤΡΙΚΗΣ ΕΠΙΒΕΒΑΙΩΣΗΣ ΑΝΤΙΚΑΤΑΣΤΑΣΗΣ…')
        else:
            self._request = None
            self.info.setText('Η αντικατάσταση ακυρώθηκε. Δεν άλλαξε η καταχώριση.')

    def _act(self, kind):
        if self._closing or self._request is not None or self._dirty or self._person is None:
            return
        if (kind == "START" and self._active) or (kind == "END" and not self._active):
            return
        self._request = PositionRequest(kind, self._person.agms, self.position.currentText(),
                                        self.direction.currentText(), (self._active or {}).get("event_id", ""))
        self._action_started = time.monotonic()
        self._action_future = self._action_worker.submit(self.endpoint.execute, self._request)
        self.info.setText("ΑΝΑΜΟΝΗ ΚΕΝΤΡΙΚΗΣ ΕΠΙΒΕΒΑΙΩΣΗΣ…")
        self._buttons()

    def _recheck(self):
        if self._closing or self._read_future is not None or self._action_future is not None:
            return
        if self._request is None and self._abandoned_reads >= MAX_ABANDONED_READS:
            return
        if self._request is not None:
            self._action_started = time.monotonic()
            self._action_future = self._action_worker.submit(self.endpoint.check, self._request)
        else:
            self._dirty = True
            self._lookup_not_before = 0.0
        self._buttons()

    def closeEvent(self, event):
        # App exit and Windows account changes are never operator END actions.
        if self._action_future is not None or self._request is not None:
            answer = QMessageBox.question(self, "Έξοδος", UNCONFIRMED +
                "\nΗ εντολή μπορεί να έχει καταχωριστεί. Να κλείσει η εφαρμογή; "
                "Στην επόμενη εκκίνηση ελέγξτε την κεντρική ενεργή θέση.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                event.ignore()
                return
        self.shutdown()
        event.accept()

    def shutdown(self):
        """GUI-thread cleanup; no waiting for SMB and no operator END."""
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._mail_timer.stop()
        self._mail_worker.close()
        self._read_worker.close()
        self._action_worker.close()

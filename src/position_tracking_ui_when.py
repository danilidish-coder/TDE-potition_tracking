"""Επιλογή ώρας ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ από τον ΑΞΥΠ, με αιτιολογία και έλεγχο."""
from __future__ import annotations
from datetime import datetime, timedelta
from PySide6.QtCore import QDate, QDateTime, QTime
from PySide6.QtWidgets import (QDateTimeEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QVBoxLayout)

DISPLAY = 'dd/MM/yyyy HH:mm'
CLOCK_TOLERANCE = timedelta(minutes=2)
OLD_TIME_LIMIT = timedelta(hours=24)


def to_qt(moment: datetime) -> QDateTime:
    return QDateTime(QDate(moment.year, moment.month, moment.day), QTime(moment.hour, moment.minute, 0))


def from_qt(value: QDateTime) -> datetime:
    date, clock = value.date(), value.time()
    return datetime(date.year(), date.month(), date.day(), clock.hour(), clock.minute())


def problem_with(moment: datetime, now: datetime, minimum: datetime | None = None,
                 minimum_text: str = '') -> tuple[str, str]:
    """(σφάλμα, ερώτηση επιβεβαίωσης). Μελλοντική ή πριν το όριο = σφάλμα· >24 ώρες πίσω = ερώτηση."""
    if moment > now + CLOCK_TOLERANCE:
        return 'Δεν επιτρέπεται μελλοντική ώρα.', ''
    if minimum is not None and moment < minimum:
        return minimum_text or 'Η ώρα προηγείται του επιτρεπτού ορίου.', ''
    if now - moment > OLD_TIME_LIMIT:
        return '', 'Η ώρα είναι πάνω από 24 ώρες πίσω. Να συνεχίσω;'
    return '', ''


def ask_moment(parent, title: str, prompt: str, default: datetime, *, reason: bool = False,
               reason_label: str = 'Αιτιολογία', info=None, minimum: datetime | None = None,
               minimum_text: str = '', now: datetime | None = None):
    """Επιστρέφει dict(moment, reason, confirm_old) ή None αν ακυρωθεί.

    info: συνάρτηση(datetime)->κείμενο που εμφανίζεται κάτω από το πεδίο ώρας
    και ανανεώνεται όσο αλλάζει η ώρα (π.χ. λίστα όσων έκαναν ΕΝΑΡΞΗ από τότε).
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel(prompt))
    form = QFormLayout()
    layout.addLayout(form)
    edit = QDateTimeEdit(to_qt(default))
    edit.setDisplayFormat(DISPLAY)
    edit.setCalendarPopup(True)
    edit.setMinimumHeight(36)
    form.addRow('Ημερομηνία και ώρα (ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ)', edit)
    details = QLabel('')
    details.setWordWrap(True)
    layout.addWidget(details)
    if info is not None:
        def refresh(*_):
            details.setText(info(from_qt(edit.dateTime())))
        edit.dateTimeChanged.connect(refresh)
        refresh()
    reason_edit = None
    if reason:
        reason_edit = QPlainTextEdit()
        reason_edit.setMaximumHeight(70)
        form.addRow(reason_label, reason_edit)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    try:
        while True:
            if dialog.exec() != QDialog.Accepted:
                return None
            moment = from_qt(edit.dateTime())
            reason_text = reason_edit.toPlainText().strip() if reason_edit is not None else ''
            if reason and len(reason_text) < 5:
                QMessageBox.warning(dialog, 'Έλεγχος', 'Η αιτιολογία απαιτεί τουλάχιστον 5 χαρακτήρες.')
                continue
            error, question = problem_with(moment, now or datetime.now(), minimum, minimum_text)
            if error:
                QMessageBox.warning(dialog, 'Έλεγχος', error)
                continue
            if question and QMessageBox.question(dialog, 'Επιβεβαίωση', question,
                                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                continue
            return dict(moment=moment, reason=reason_text, confirm_old=bool(question))
    finally:
        dialog.deleteLater()

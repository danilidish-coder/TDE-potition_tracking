"""Current report actions and finalized-shift archive search dialog."""
from __future__ import annotations
from datetime import datetime
from position_tracking_common import _clean, format_when
from position_tracking_pdf import create_shift_pdf
from position_tracking_settings import _open_path
from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import QDateEdit, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QDialog, QListWidget, QListWidgetItem, QCheckBox


class ReportDialogsMixin:
    def _report(self):
        if not self.store:
            QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
        shift = self.store.sync_active_shift()
        if not shift:
            shift = self.store.current_report_shift()
        if not shift:
            QMessageBox.information(self, "Τρέχον έντυπο", "Δεν υπάρχει διαθέσιμη τρέχουσα αναφορά."); return
        try:
            path = create_shift_pdf(self.store, shift, self._people_by_agms)
            self._services.open_path(path)
        except Exception as exc:
            QMessageBox.critical(self, "PDF", str(exc))


    def _open_files(self):
        if not self.store:
            QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
        try:
            self._services.open_path(self.store.archive)
        except Exception as exc:
            QMessageBox.critical(self, "Αρχεία", str(exc))


    def _report_archive(self):
        if not self.store:
            QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ ΒΑΡΔΙΑΣ")
        dlg.resize(900, 650)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        title = QLabel("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ ΒΑΡΔΙΑΣ")
        title.setStyleSheet("font-size:18px;font-weight:900")
        lay.addWidget(title)

        hint = QLabel(
            "Εμφανίζονται αρχικά οι 20 πιο πρόσφατες βάρδιες. "
            "Χρησιμοποιήστε ημερομηνίες ή/και Αξιωματικό Υπηρεσίας για παλαιότερη αναζήτηση."
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        filters = QFormLayout()
        date_filter = QCheckBox("Χρήση ημερομηνιών")
        from_date = QDateEdit()
        to_date = QDateEdit()
        from_date.setCalendarPopup(True)
        to_date.setCalendarPopup(True)
        from_date.setDisplayFormat("dd/MM/yyyy")
        to_date.setDisplayFormat("dd/MM/yyyy")
        from_date.setDate(QDate.currentDate().addMonths(-1))
        to_date.setDate(QDate.currentDate())
        from_date.setEnabled(False)
        to_date.setEnabled(False)
        officer_edit = QLineEdit()
        officer_edit.setPlaceholderText("Επώνυμο, όνομα ή Α.Γ.Μ.Σ. Αξιωματικού")
        filters.addRow("", date_filter)
        filters.addRow("Από", from_date)
        filters.addRow("Έως", to_date)
        filters.addRow("Αξιωματικός", officer_edit)
        lay.addLayout(filters)

        actions = QHBoxLayout()
        search_btn = QPushButton("ΑΝΑΖΗΤΗΣΗ")
        clear_btn = QPushButton("ΚΑΘΑΡΙΣΜΟΣ")
        actions.addWidget(search_btn)
        actions.addWidget(clear_btn)
        actions.addStretch()
        lay.addLayout(actions)

        listing = QListWidget()
        lay.addWidget(listing, 1)
        info = QLabel("")
        lay.addWidget(info)

        buttons = QHBoxLayout()
        open_btn = QPushButton("ΑΝΟΙΓΜΑ ΑΝΑΦΟΡΑΣ")
        close_btn = QPushButton("ΚΛΕΙΣΙΜΟ")
        buttons.addWidget(open_btn)
        buttons.addStretch()
        buttons.addWidget(close_btn)
        lay.addLayout(buttons)

        current_results: list[dict] = []

        def shift_label(shift: dict) -> str:
            try:
                start_at = datetime.fromisoformat(_clean(shift.get("start_at")))
                end_at = datetime.fromisoformat(_clean(shift.get("end_at")))
                period = f"{start_at:%d/%m/%Y %H:%M} – {end_at:%d/%m/%Y %H:%M}"
            except Exception:
                period = format_when(shift.get("start_at"))
            officer = shift.get("start_officer") or shift.get("end_officer") or {}
            officer_name = _clean(
                f"{officer.get('rank','')} {officer.get('surname','')} {officer.get('given_name','')}"
            ) or _clean(officer.get("full_name")) or "ΧΩΡΙΣ ΟΝΟΜΑ"
            return f"{period}  |  {officer_name}"

        def fill_results(shifts: list[dict], default_view: bool = False):
            nonlocal current_results
            current_results = shifts
            listing.clear()
            for shift in shifts:
                item = QListWidgetItem(shift_label(shift))
                item.setData(Qt.UserRole, _clean(shift.get("shift_id")))
                listing.addItem(item)
            if default_view:
                info.setText(f"Τελευταίες ολοκληρωμένες βάρδιες: {len(shifts)}")
            else:
                info.setText(f"Βρέθηκαν {len(shifts)} βάρδιες.")
            if shifts:
                listing.setCurrentRow(0)

        def show_recent():
            fill_results(self.store.search_finalized_shifts(limit=20), default_view=True)

        def do_search():
            use_dates = date_filter.isChecked()
            d_from = from_date.date().toPython() if use_dates else None
            d_to = to_date.date().toPython() if use_dates else None
            if d_from and d_to and d_from > d_to:
                QMessageBox.warning(dlg, "Αναφορές", "Η ημερομηνία «Από» είναι μετά την ημερομηνία «Έως».")
                return
            officer_query = _clean(officer_edit.text())
            if not use_dates and not officer_query:
                show_recent()
                return
            shifts = self.store.search_finalized_shifts(
                date_from=d_from,
                date_to=d_to,
                officer_query=officer_query,
            )
            fill_results(shifts)

        def clear_filters():
            date_filter.setChecked(False)
            from_date.setDate(QDate.currentDate().addMonths(-1))
            to_date.setDate(QDate.currentDate())
            officer_edit.clear()
            show_recent()

        def selected_shift():
            item = listing.currentItem()
            if not item:
                return None
            sid = _clean(item.data(Qt.UserRole))
            return next((s for s in current_results if _clean(s.get("shift_id")) == sid), None)

        def open_report():
            shift = selected_shift()
            if not shift:
                QMessageBox.warning(dlg, "Αναφορές", "Επιλέξτε πρώτα μία βάρδια.")
                return
            try:
                path = create_shift_pdf(self.store, shift, self._people_by_agms)
                self._services.open_path(path)
            except Exception as exc:
                QMessageBox.critical(dlg, "Αναφορές", str(exc))

        date_filter.toggled.connect(from_date.setEnabled)
        date_filter.toggled.connect(to_date.setEnabled)
        search_btn.clicked.connect(do_search)
        clear_btn.clicked.connect(clear_filters)
        open_btn.clicked.connect(open_report)
        listing.itemDoubleClicked.connect(lambda *_: open_report())
        officer_edit.returnPressed.connect(do_search)
        close_btn.clicked.connect(dlg.accept)

        show_recent()
        dlg.exec()


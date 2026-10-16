from __future__ import annotations

import json
import base64
import os
import hashlib
import shutil
import re
import sqlite3
import subprocess
import socket
import sys
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import zipfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, date, timedelta, time as dtime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from position_tracking_offline import OfflineJournal, OfflineConflict
from position_tracking_windows_session import _windows_session_is_active
from position_tracking_machine_queue import _local_root, _machine_queue_root
from position_tracking_handoff import close_previous_windows_user_positions, reconcile_handoff_before_replay
from position_tracking_bootstrap import cache_windows_client
from position_tracking_common import _clean, _norm_search, _safe_name
from xml.etree import ElementTree as ET
from position_tracking_artwork import POLICE_EMBLEM_PNG_B64, GREECE_MAP_SVG_B64
from position_tracking_store import SharedEventStore
from position_tracking_statistics import (create_personnel_statistics_xlsx)
from position_tracking_documents import (create_shift_docx, archive_shift_docx)
from position_tracking_pdf import (create_shift_pdf, summarize_personnel_history, create_personnel_history_pdf, archive_shift_pdf)
from position_tracking_report_text import (GREEK_MONTH_GENITIVE, _duration_text, build_shift_text, build_roster_shift_text, _format_seconds, shift_report_title, build_roster_shift_html, _escape_html, build_shift_html)

APP_NAME = "TDE Krystallopigis - Katagrafi Theseon"
APP_VERSION = "1.2.5"
SETTINGS_NAME = "position_tracking.settings.json"
DEFAULT_CUTOFF = "10:00"
STATISTICS_PIN_SHA256 = "ca444860f0e1ddca9596007253ea43b3a5133780b0a566d9a096a53568c063fb"

# Exact approved shared visual assets from TDE-Control-Center/SHARED_ASSETS.


from position_tracking_settings import (
    AppConfig as _AppConfig, _app_dir, _open_path, _fallback_settings_path,
    _runtime_root as _settings_runtime_root,
)


def _exe_dir() -> Path:
    return _app_dir()


def _runtime_root() -> Path:
    return _settings_runtime_root(_app_dir())


def _settings_path() -> Path:
    return _local_root() / SETTINGS_NAME


class AppConfig(_AppConfig):
    """Compatibility facade preserving legacy overridable path providers."""

    @classmethod
    def load(cls) -> "AppConfig":
        return super().load(path=_settings_path(), app_directory=_app_dir())

    def save(self) -> Path:
        return super().save(path=_settings_path())




from position_tracking_personnel import PersonnelRecord, PersonnelRepository, ShiftRosterRepository


from position_tracking_store_io import BusyError



















































def run(args=None) -> int:
    from position_tracking_ui_shifts import ShiftControllerMixin
    from position_tracking_ui_shift_end import ShiftEndDialogMixin
    from position_tracking_ui_lifecycle import WindowLifecycleMixin
    from position_tracking_ui_positions import PositionActionsMixin
    from position_tracking_ui_selection import PersonnelSelectionMixin
    from position_tracking_ui_messages import MessageDialogsMixin
    from position_tracking_ui_communication import CommunicationMixin
    from position_tracking_ui_context import WindowServices
    from position_tracking_ui_configuration import ConfigurationMixin
    from position_tracking_ui_view import MainViewMixin
    from position_tracking_ui_map import BoothMapWidget, LiveMapDialog
    from position_tracking_ui_assets import _police_emblem_pixmap, GreeceMapWidget, ArrowComboBox, _network_icon
    from position_tracking_theme import THEME_DARK, THEME_LIGHT, _theme_stylesheet
    from position_tracking_rendering import coherent_widget_update
    from PySide6.QtCore import Qt, QDate, QDateTime, QTime, QTimer, QRectF, QPointF, QByteArray
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QIcon, QPixmap, QPalette, QPainterPath
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import (
        QApplication, QComboBox, QDateEdit, QFormLayout, QFrame, QHBoxLayout,
        QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
        QInputDialog, QDialog, QDateTimeEdit, QSpinBox, QListWidget, QListWidgetItem, QFileDialog, QToolButton,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, QTimeEdit, QPlainTextEdit
    )











    class MainWindow(ShiftControllerMixin, ShiftEndDialogMixin, WindowLifecycleMixin, PositionActionsMixin, PersonnelSelectionMixin, MessageDialogsMixin, CommunicationMixin, ConfigurationMixin, MainViewMixin, QMainWindow):
        def __init__(self):
            super().__init__()
            self._services = WindowServices(AppConfig, _app_dir, _local_root, _machine_queue_root, _open_path)
            self.config = self._services.config_type.load()
            self.people: tuple[PersonnelRecord, ...] = ()
            self._people_by_agms: dict[str, PersonnelRecord] = {}
            self.store: SharedEventStore | None = None
            self._pending_prompt_active = False
            self._last_shift_signature = ""
            self._force_exit = False
            self._message_dialog_active = False
            self._app_started_at = datetime.now().isoformat(timespec="seconds")
            self.client_id = SharedEventStore.local_client_id()
            self._network_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="TDE-network")
            # Network heartbeat/shift polling must never starve a booth action
            # when the SMB host disconnects or an old worker blocks in I/O.
            self._position_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TDE-position")
            self._state_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="TDE-state")
            self._position_operation_future = None
            self._last_bootstrap_check = 0.0
            self._offline_future = None
            self._offline_polling = False
            self._pending_central_store = None
            self._handoff_initial_error = ""
            self.offline = OfflineJournal(_machine_queue_root())
            self._agms_query_serial = 0
            self._shift_status_future = None
            self._communication_future = None
            self._shift_future = None
            self.setWindowTitle(f"Τ.Δ.Ε. Κρυσταλλοπηγής - Καταγραφή Θέσεων v{APP_VERSION}")
            emblem_icon = _police_emblem_pixmap(96)
            if not emblem_icon.isNull():
                self.setWindowIcon(QIcon(emblem_icon))
            self.resize(1160, 720)
            self.setMinimumSize(1000, 650)
            self._build()
            self._apply_config()
            self._apply_theme()
            self.shift_timer = QTimer(self)
            self.shift_timer.timeout.connect(self._check_shift_updates)
            self.shift_timer.start(3000)
            self.communication_timer = QTimer(self)
            self.communication_timer.timeout.connect(self._communication_tick)
            self.communication_timer.start(2500)
            QApplication.instance().aboutToQuit.connect(self._cleanup_client)
            self.offline_timer = QTimer(self)
            self.offline_timer.timeout.connect(self._offline_tick)
            self.offline_timer.start(3000)
            self._offline_tick()
            self._communication_tick()







































        def _live_map(self):
            if not self.store:
                QMessageBox.warning(self,"Έλεγχος","Δεν είναι διαθέσιμος ο φάκελος δεδομένων."); return
            LiveMapDialog(self.store, self._people_by_agms, self._officer_selected, self).exec()


        def _backup(self):
            if not self.store:
                QMessageBox.warning(self, "Backup", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            try:
                path = self.store.backup_data()
                QMessageBox.information(self, "Backup", f"Το αντίγραφο ασφαλείας δημιουργήθηκε:\n{path}")
            except Exception as exc:
                QMessageBox.critical(self, "Backup", str(exc))

        def _audit_view(self):
            if not self.store:
                QMessageBox.warning(self, "Audit log", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            path = self.store.audit / "admin_audit.jsonl"
            if not path.exists():
                QMessageBox.information(self, "Ιστορικό ενεργειών", "Δεν υπάρχουν ακόμη καταγραφές ενεργειών.")
                return
            dlg = QDialog(self); dlg.setWindowTitle("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ - Ιστορικό ενεργειών"); dlg.resize(900, 600)
            lay = QVBoxLayout(dlg); browser = QTextBrowser(); browser.setStyleSheet("font-family:Consolas,monospace")
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
            pretty=[]
            for line in lines:
                try:
                    r=json.loads(line); pretty.append(f"{r.get('timestamp','')} | {r.get('user','')}@{r.get('computer','')} | {r.get('action','')} | {json.dumps(r.get('details',{}),ensure_ascii=False)}")
                except Exception:
                    pretty.append(line)
            browser.setPlainText("\n".join(pretty)); lay.addWidget(browser); dlg.exec()

        def _admin(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
            try:
                self.store.log_admin_action("OFFICER_DUTY_PANEL_OPENED")
            except Exception:
                pass
            dlg = QDialog(self); dlg.setWindowTitle("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ"); dlg.resize(720, 620)
            t = THEME_DARK if _clean(self.config.theme).lower() == "dark" else THEME_LIGHT
            dlg.setStyleSheet(_theme_stylesheet(self.config.theme))
            lay = QVBoxLayout(dlg); lay.setContentsMargins(24,22,24,22); lay.setSpacing(10)
            header = QLabel("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ"); header.setStyleSheet(f"font-size:20px;font-weight:900;color:{t['text']}")
            lay.addWidget(header)
            officer_agms = QLineEdit(); officer_agms.setPlaceholderText("Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας")
            officer_name = QLabel("—"); officer_name.setStyleSheet("font-weight:800;font-size:15px")
            form = QFormLayout(); form.addRow("Α.Γ.Μ.Σ.", officer_agms); form.addRow("Αξιωματικός", officer_name); lay.addLayout(form)
            status = QLabel(""); status.setWordWrap(True); status.setStyleSheet(
                f"background:{t['card2']};color:{t['text']};border:1px solid {t['border']};border-radius:10px;padding:9px;font-weight:700"
            )
            lay.addWidget(status)
            members = QListWidget(); lay.addWidget(members, 1)
            row = QHBoxLayout()
            accept_btn = QPushButton("ΑΠΟΔΟΧΗ"); exclude_btn = QPushButton("ΕΞΑΙΡΕΣΗ"); refresh_btn = QPushButton("ΑΝΑΝΕΩΣΗ")
            row.addWidget(accept_btn); row.addWidget(exclude_btn); row.addWidget(refresh_btn); lay.addLayout(row)
            row2 = QHBoxLayout()
            start_shift = QPushButton("ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ"); end_shift = QPushButton("ΛΗΞΗ ΒΑΡΔΙΑΣ"); live = QPushButton("ΖΩΝΤΑΝΗ ΕΙΚΟΝΑ")
            start_shift.setMinimumHeight(48); end_shift.setMinimumHeight(48)
            row2.addWidget(start_shift); row2.addWidget(end_shift); row2.addWidget(live); lay.addLayout(row2)

            def selected_officer():
                return self._people_by_agms.get(_clean(officer_agms.text()))

            def officer_changed(*_):
                p = selected_officer()
                officer_name.setText(_clean(f"{p.rank} {p.full_name}") if p else "—")

            def refresh_members():
                shift = self.store.sync_active_shift() if self.store else None
                members.clear()
                if not shift:
                    status.setText("Δεν υπάρχει ενεργή βάρδια.")
                    accept_btn.setEnabled(False); exclude_btn.setEnabled(False); end_shift.setEnabled(False); start_shift.setEnabled(True)
                    return
                start_shift.setEnabled(False); end_shift.setEnabled(True); accept_btn.setEnabled(True); exclude_btn.setEnabled(True)
                st = datetime.fromisoformat(shift["start_at"])
                off = shift.get("start_officer") or {}
                status.setText(f"Ενεργή βάρδια από {st:%d/%m/%Y %H:%M} — Αξιωματικός: {_clean(f"{off.get('rank','')} {off.get('full_name','')}")}")
                for state_key, label in (("approved", "ΑΠΟΔΕΚΤΟΣ"), ("pending", "ΑΝΑΜΟΝΗ"), ("excluded", "ΕΞΑΙΡΕΣΗ")):
                    for agms in shift.get(state_key, []):
                        person = self._people_by_agms.get(_clean(agms))
                        name = _clean(f"{person.rank} {person.full_name}") if person else f"ΑΓΜΣ {agms}"
                        members.addItem(f"{label} | {agms} | {name}")
                        item = members.item(members.count()-1); item.setData(Qt.UserRole, _clean(agms))

            def change_state(state):
                item = members.currentItem()
                if not item:
                    QMessageBox.warning(dlg, "Έλεγχος", "Επιλέξτε πρώτα άτομο."); return
                if state == "EXCLUDED":
                    agms = _clean(item.data(Qt.UserRole))
                    person = self._people_by_agms.get(agms)
                    name = _clean(f"{person.rank} {person.full_name}") if person else f"ΑΓΜΣ {agms}"
                    confirm = QMessageBox.question(
                        dlg,
                        "Επιβεβαίωση εξαίρεσης",
                        f"{name}\n\nΕίστε βέβαιοι ότι θέλετε να ΕΞΑΙΡΕΣΕΤΕ το άτομο από τη βάρδια;",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if confirm != QMessageBox.Yes:
                        return
                try:
                    self.store.set_shift_member_state(item.data(Qt.UserRole), state); refresh_members()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Βάρδια", str(exc))

            def do_start():
                p = selected_officer()
                if not p:
                    QMessageBox.warning(dlg, "Έλεγχος", "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
                try:
                    shift = self.store.start_officer_shift(p)
                    QMessageBox.information(dlg, "Βάρδια", f"Έναρξη βάρδιας {shift['start_at'].replace('T',' ')}.\nΕλέγξτε τους ΑΠΟΔΕΚΤΟΥΣ και εξαιρέστε όποιον ανήκει στην προηγούμενη βάρδια.")
                    refresh_members()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Βάρδια", str(exc))

            def do_end():
                p = selected_officer()
                if not p:
                    QMessageBox.warning(dlg, "Έλεγχος", "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
                try:
                    if self._confirm_and_end_officer_shift(p):
                        refresh_members()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Λήξη βάρδιας", str(exc))

            officer_agms.textChanged.connect(officer_changed)
            accept_btn.clicked.connect(lambda: change_state("APPROVED")); exclude_btn.clicked.connect(lambda: change_state("EXCLUDED")); refresh_btn.clicked.connect(refresh_members)
            start_shift.clicked.connect(do_start); end_shift.clicked.connect(do_end); live.clicked.connect(self._live_map)
            timer = QTimer(dlg); timer.timeout.connect(refresh_members); timer.start(2500)
            refresh_members(); dlg.exec()

        def _live_map(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Ορίστε πρώτα κεντρικό φάκελο δεδομένων.")
                return
            LiveMapDialog(self.store, self._people_by_agms, self._officer_selected, self).exec()


        def _add_position(self):
            value, ok = QInputDialog.getText(self, "Νέα θέση", "Ονομασία / αριθμός θέσης")
            value = _clean(value)
            if ok and value:
                existing = [self.position.itemText(i) for i in range(self.position.count())]
                if value not in existing: self.position.addItem(value)
                self.position.setCurrentText(value); self._save_config()

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
                _open_path(path)
            except Exception as exc:
                QMessageBox.critical(self, "PDF", str(exc))

        def _open_files(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime."); return
            try:
                _open_path(self.store.archive)
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
                    period = _clean(shift.get("start_at")).replace("T", " ")
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
                    _open_path(path)
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

        def _personnel_history(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime.")
                return
            pin, ok = QInputDialog.getText(self, "Ιστορικό προσωπικού", "Κωδικός πρόσβασης", QLineEdit.Password)
            if not ok:
                return
            if hashlib.sha256(_clean(pin).encode("utf-8")).hexdigest() != STATISTICS_PIN_SHA256:
                QMessageBox.warning(self, "Ιστορικό προσωπικού", "Λανθασμένος κωδικός.")
                return

            dlg = QDialog(self)
            dlg.setWindowTitle("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
            dlg.resize(1180, 780)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 18, 20, 18)
            lay.setSpacing(9)

            title = QLabel("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
            title.setStyleSheet("font-size:18px;font-weight:900")
            lay.addWidget(title)
            hint = QLabel(
                "Βασικές αναζητήσεις: «ΠΟΥ/ΠΟΤΕ ΔΟΥΛΕΨΕ Ο ΤΑΔΕ;» ή «ΠΟΙΟΣ ΗΤΑΝ ΕΚΕΙ ΤΟΤΕ;». "
                "Τα υπόλοιπα φίλτρα είναι προαιρετικά και συνδυάζονται μεταξύ τους."
            )
            hint.setWordWrap(True)
            lay.addWidget(hint)

            workers = self.store.list_personnel_workers()
            person_combo = ArrowComboBox()
            person_combo.setEditable(True)
            person_combo.addItem("ΟΛΟΙ ΟΣΟΙ ΕΧΟΥΝ ΔΟΥΛΕΨΕΙ", "")
            for worker in workers:
                label = _clean(
                    f"{worker.get('rank','')} {worker.get('surname','')} {worker.get('given_name','')} "
                    f"(ΑΓΜΣ {worker.get('agms','')})"
                )
                person_combo.addItem(label, _clean(worker.get("agms")))

            use_dates = QCheckBox("Φίλτρο ημερομηνιών")
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

            positions = self.store.list_session_positions()
            position_combo = ArrowComboBox()
            position_combo.addItem("ΟΛΕΣ")
            for pos in positions:
                position_combo.addItem(pos)
            direction_combo = ArrowComboBox()
            direction_combo.addItems(["ΟΛΑ", "ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"])

            use_clock = QCheckBox("Φίλτρο ώρας μέσα στην ημέρα")
            time_from = QTimeEdit()
            time_to = QTimeEdit()
            time_from.setDisplayFormat("HH:mm")
            time_to.setDisplayFormat("HH:mm")
            time_from.setTime(QTime(0, 0))
            time_to.setTime(QTime(23, 59))
            time_from.setEnabled(False)
            time_to.setEnabled(False)

            exact_moment = QCheckBox("Στιγμιαία αναζήτηση — ποιος ήταν εκεί τότε")
            moment_date = QDateEdit()
            moment_time = QTimeEdit()
            moment_date.setCalendarPopup(True)
            moment_date.setDisplayFormat("dd/MM/yyyy")
            moment_date.setDate(QDate.currentDate())
            moment_time.setDisplayFormat("HH:mm")
            moment_time.setTime(QTime.currentTime())
            moment_date.setEnabled(False)
            moment_time.setEnabled(False)

            min_duration = QSpinBox()
            max_duration = QSpinBox()
            for box in (min_duration, max_duration):
                box.setRange(0, 24 * 60)
                box.setSuffix(" λεπτά")
                box.setSpecialValueText("Χωρίς όριο")
            min_duration.setToolTip("Ελάχιστη διάρκεια μίας συνεχόμενης παραμονής στη θέση")
            max_duration.setToolTip("Μέγιστη διάρκεια μίας συνεχόμενης παραμονής στη θέση")

            form = QFormLayout()
            form.addRow("Άτομο", person_combo)
            form.addRow("", use_dates)
            form.addRow("Από ημερομηνία", from_date)
            form.addRow("Έως ημερομηνία", to_date)
            form.addRow("Θέση", position_combo)
            form.addRow("Κατεύθυνση", direction_combo)
            form.addRow("", use_clock)
            form.addRow("Ώρα από", time_from)
            form.addRow("Ώρα έως", time_to)
            form.addRow("", exact_moment)
            form.addRow("Ημερομηνία στιγμής", moment_date)
            form.addRow("Ώρα στιγμής", moment_time)
            form.addRow("Διάρκεια από", min_duration)
            form.addRow("Διάρκεια έως", max_duration)
            lay.addLayout(form)

            quick = QHBoxLayout()
            person_mode_btn = QPushButton("ΠΟΥ / ΠΟΤΕ ΔΟΥΛΕΨΕ Ο ΤΑΔΕ;")
            moment_mode_btn = QPushButton("ΠΟΙΟΣ ΗΤΑΝ ΕΚΕΙ ΤΟΤΕ;")
            quick.addWidget(person_mode_btn)
            quick.addWidget(moment_mode_btn)
            quick.addStretch()
            lay.addLayout(quick)

            actions = QHBoxLayout()
            search_btn = QPushButton("ΑΝΑΖΗΤΗΣΗ")
            clear_btn = QPushButton("ΚΑΘΑΡΙΣΜΟΣ")
            pdf_btn = QPushButton("PDF ΑΠΟΤΕΛΕΣΜΑΤΩΝ")
            actions.addWidget(search_btn)
            actions.addWidget(clear_btn)
            actions.addWidget(pdf_btn)
            actions.addStretch()
            lay.addLayout(actions)

            summary_box = QLabel("")
            summary_box.setWordWrap(True)
            summary_box.setObjectName("infoBox")
            lay.addWidget(summary_box)

            result_label = QLabel("")
            lay.addWidget(result_label)

            table = QTableWidget(0, 8)
            table.setHorizontalHeaderLabels(
                ["ΗΜΕΡΟΜΗΝΙΑ", "ΑΓΜΣ", "ΟΝΟΜΑ", "ΘΕΣΗ", "ΚΑΤΕΥΘΥΝΣΗ", "ΕΝΑΡΞΗ", "ΛΗΞΗ", "ΔΙΑΡΚΕΙΑ"]
            )
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)
            lay.addWidget(table, 1)

            current_rows: list[dict] = []
            current_criteria = ""

            def qtime_to_time(value: QTime) -> dtime:
                return dtime(value.hour(), value.minute())

            def selected_person_query() -> str:
                text_value = _clean(person_combo.currentText())
                if _norm_search(text_value) == _norm_search("ΟΛΟΙ ΟΣΟΙ ΕΧΟΥΝ ΔΟΥΛΕΨΕΙ"):
                    return ""
                idx = person_combo.currentIndex()
                if idx >= 0 and text_value == _clean(person_combo.itemText(idx)):
                    data = person_combo.itemData(idx)
                    if _clean(data):
                        return _clean(data)
                return text_value

            def summary_text(rows: list[dict]) -> str:
                summary = summarize_personnel_history(rows)
                line1 = (
                    f"Καταχωρίσεις: {len(rows)}   |   Άτομα: {summary['people']}   |   "
                    f"Συνολικός χρόνος: {_format_seconds(summary['total_seconds'])}"
                )
                parts = [line1]
                for direction in ("ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"):
                    sec = int(summary["by_direction"].get(direction, 0))
                    if not sec:
                        continue
                    pos_parts = []
                    for (d, pos), psec in sorted(summary["by_direction_position"].items(), key=lambda x: (x[0][0], x[0][1])):
                        if d == direction and psec:
                            pos_parts.append(f"Θέση {pos}: {_format_seconds(psec)}")
                    detail = " · ".join(pos_parts)
                    parts.append(f"{direction}: {_format_seconds(sec)}" + (f"   |   {detail}" if detail else ""))
                return "\n".join(parts)

            def criteria_text() -> str:
                bits = []
                pq = selected_person_query()
                if pq:
                    bits.append(f"Άτομο: {person_combo.currentText()}")
                else:
                    bits.append("Άτομο: ΟΛΟΙ")
                if exact_moment.isChecked():
                    bits.append(
                        f"Στιγμή: {moment_date.date().toString('dd/MM/yyyy')} {moment_time.time().toString('HH:mm')}"
                    )
                elif use_dates.isChecked():
                    bits.append(
                        f"Ημερομηνίες: {from_date.date().toString('dd/MM/yyyy')}–{to_date.date().toString('dd/MM/yyyy')}"
                    )
                pos = _clean(position_combo.currentText())
                direction = _clean(direction_combo.currentText())
                if pos != "ΟΛΕΣ":
                    bits.append(f"Θέση: {pos}")
                if direction != "ΟΛΑ":
                    bits.append(f"Κατεύθυνση: {direction}")
                if use_clock.isChecked() and not exact_moment.isChecked():
                    bits.append(f"Ώρες: {time_from.time().toString('HH:mm')}–{time_to.time().toString('HH:mm')}")
                if min_duration.value():
                    bits.append(f"Διάρκεια ≥ {min_duration.value()} λεπτά")
                if max_duration.value():
                    bits.append(f"Διάρκεια ≤ {max_duration.value()} λεπτά")
                return " | ".join(bits)

            def render_rows(rows: list[dict], label_prefix: str = "Βρέθηκαν"):
                nonlocal current_rows, current_criteria
                current_rows = rows
                current_criteria = criteria_text()
                table.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    try:
                        sdt = datetime.fromisoformat(row["start_at"])
                        edt = datetime.fromisoformat(row["end_at"])
                        date_text = sdt.strftime("%d/%m/%Y")
                        start_text = sdt.strftime("%H:%M:%S")
                        end_text = edt.strftime("%H:%M:%S")
                    except Exception:
                        date_text = _clean(row.get("start_at"))[:10]
                        start_text = _clean(row.get("start_at"))[11:19]
                        end_text = _clean(row.get("end_at"))[11:19]
                    name = _clean(f"{row.get('rank','')} {row.get('surname','')} {row.get('given_name','')}") or _clean(row.get("full_name"))
                    values = [
                        date_text,
                        _clean(row.get("agms")),
                        name,
                        _clean(row.get("position")),
                        _clean(row.get("direction")),
                        start_text,
                        end_text,
                        _format_seconds(int(row.get("duration_seconds") or 0)),
                    ]
                    for col, value in enumerate(values):
                        table.setItem(r, col, QTableWidgetItem(str(value)))
                result_label.setText(f"{label_prefix} {len(rows)} καταχωρίσεις.")
                summary_box.setText(summary_text(rows) if rows else "Δεν βρέθηκαν καταχωρίσεις με αυτά τα κριτήρια.")

            def do_search():
                d_from = from_date.date().toPython() if use_dates.isChecked() and not exact_moment.isChecked() else None
                d_to = to_date.date().toPython() if use_dates.isChecked() and not exact_moment.isChecked() else None
                if d_from and d_to and d_from > d_to:
                    QMessageBox.warning(dlg, "Ιστορικό", "Η ημερομηνία «Από» είναι μετά την ημερομηνία «Έως».")
                    return
                moment = None
                if exact_moment.isChecked():
                    qd = moment_date.date()
                    qt = moment_time.time()
                    moment = datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute())
                tf = qtime_to_time(time_from.time()) if use_clock.isChecked() and not exact_moment.isChecked() else None
                tt = qtime_to_time(time_to.time()) if use_clock.isChecked() and not exact_moment.isChecked() else None
                if max_duration.value() and min_duration.value() and max_duration.value() < min_duration.value():
                    QMessageBox.warning(dlg, "Ιστορικό", "Η μέγιστη διάρκεια είναι μικρότερη από την ελάχιστη.")
                    return

                rows = self.store.search_personnel_sessions(
                    person_query=selected_person_query(),
                    date_from=d_from,
                    date_to=d_to,
                    position=_clean(position_combo.currentText()),
                    direction=_clean(direction_combo.currentText()),
                    time_from=tf,
                    time_to=tt,
                    moment=moment,
                    min_duration_minutes=min_duration.value(),
                    max_duration_minutes=max_duration.value(),
                )
                render_rows(rows)
                try:
                    self.store.log_admin_action("PERSONNEL_HISTORY_SEARCH", {
                        "criteria": criteria_text(), "results": len(rows)
                    })
                except Exception:
                    pass

            def clear_search():
                person_combo.setCurrentIndex(0)
                use_dates.setChecked(False)
                from_date.setDate(QDate.currentDate().addMonths(-1))
                to_date.setDate(QDate.currentDate())
                position_combo.setCurrentIndex(0)
                direction_combo.setCurrentIndex(0)
                use_clock.setChecked(False)
                time_from.setTime(QTime(0, 0))
                time_to.setTime(QTime(23, 59))
                exact_moment.setChecked(False)
                moment_date.setDate(QDate.currentDate())
                moment_time.setTime(QTime.currentTime())
                min_duration.setValue(0)
                max_duration.setValue(0)
                rows = self.store.search_personnel_sessions(limit=100)
                render_rows(rows, "Τελευταίες")

            def export_pdf():
                if not current_rows:
                    QMessageBox.warning(dlg, "PDF", "Δεν υπάρχουν αποτελέσματα για εξαγωγή.")
                    return
                try:
                    path = create_personnel_history_pdf(
                        current_rows,
                        current_criteria,
                        summarize_personnel_history(current_rows),
                    )
                    _open_path(path)
                except Exception as exc:
                    QMessageBox.critical(dlg, "PDF", str(exc))

            def update_filter_states():
                moment_on = exact_moment.isChecked()
                date_on = use_dates.isChecked() and not moment_on
                clock_on = use_clock.isChecked() and not moment_on
                from_date.setEnabled(date_on)
                to_date.setEnabled(date_on)
                time_from.setEnabled(clock_on)
                time_to.setEnabled(clock_on)
                moment_date.setEnabled(moment_on)
                moment_time.setEnabled(moment_on)
                use_dates.setEnabled(not moment_on)
                use_clock.setEnabled(not moment_on)

            def choose_person_mode():
                exact_moment.setChecked(False)
                person_combo.setFocus()
                if person_combo.lineEdit():
                    person_combo.lineEdit().selectAll()

            def choose_moment_mode():
                person_combo.setCurrentIndex(0)
                exact_moment.setChecked(True)
                position_combo.setCurrentIndex(0)
                direction_combo.setCurrentIndex(0)
                moment_date.setFocus()

            use_dates.toggled.connect(update_filter_states)
            use_clock.toggled.connect(update_filter_states)
            exact_moment.toggled.connect(update_filter_states)
            search_btn.clicked.connect(do_search)
            clear_btn.clicked.connect(clear_search)
            pdf_btn.clicked.connect(export_pdf)
            person_mode_btn.clicked.connect(choose_person_mode)
            moment_mode_btn.clicked.connect(choose_moment_mode)
            person_combo.lineEdit().returnPressed.connect(do_search)

            update_filter_states()
            rows = self.store.search_personnel_sessions(limit=100)
            render_rows(rows, "Τελευταίες")
            dlg.exec()

        def _snapshot(self):
            if not self.store:
                QMessageBox.warning(self, "Έλεγχος", "Ορίστε κεντρικό φάκελο."); return
            active = self.store.active_all()
            if not active:
                QMessageBox.information(self,"Στιγμιαία εικόνα","Δεν υπάρχουν ανοικτές θέσεις."); return
            lines = [f"{x.get('rank','')} {x.get('full_name','')} — Θ. {x.get('position','')} {x.get('direction','')} — από {x.get('timestamp','').replace('T',' ')}" for x in active]
            QMessageBox.information(self,"Στιγμιαία εικόνα","\n".join(lines))


    app = QApplication(list(args or sys.argv))
    app.setApplicationName("TDE Position Tracking")
    try:
        window = MainWindow()
    except RuntimeError as exc:
        # Fail closed on an inaccessible shared queue or old pending records.
        QMessageBox.critical(None, "ΚΟΙΝΗ ΟΥΡΑ ΘΕΣΕΩΝ — ΑΣΦΑΛΕΙΑ", str(exc))
        return 2
    from position_tracking_ui_presentation import arm_initial_presentation
    presentation = arm_initial_presentation(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())

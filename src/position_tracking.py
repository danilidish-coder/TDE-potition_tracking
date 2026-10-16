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
from position_tracking_constants import APP_NAME, APP_VERSION, STATISTICS_PIN_SHA256
from position_tracking_artwork import POLICE_EMBLEM_PNG_B64, GREECE_MAP_SVG_B64
from position_tracking_store import SharedEventStore
from position_tracking_statistics import (create_personnel_statistics_xlsx)
from position_tracking_documents import (create_shift_docx, archive_shift_docx)
from position_tracking_pdf import (create_shift_pdf, summarize_personnel_history, create_personnel_history_pdf, archive_shift_pdf)
from position_tracking_report_text import (GREEK_MONTH_GENITIVE, _duration_text, build_shift_text, build_roster_shift_text, _format_seconds, shift_report_title, build_roster_shift_html, _escape_html, build_shift_html)

SETTINGS_NAME = "position_tracking.settings.json"
DEFAULT_CUTOFF = "10:00"

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
    from position_tracking_ui_history import PersonnelHistoryMixin
    from position_tracking_ui_reports import ReportDialogsMixin
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











    class MainWindow(PersonnelHistoryMixin, ReportDialogsMixin, ShiftControllerMixin, ShiftEndDialogMixin, WindowLifecycleMixin, PositionActionsMixin, PersonnelSelectionMixin, MessageDialogsMixin, CommunicationMixin, ConfigurationMixin, MainViewMixin, QMainWindow):
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

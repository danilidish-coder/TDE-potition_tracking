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











    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            # Let the complete Qt backing-store paint supply the first content;
            # avoid a separate native system-background erase on exposure.
            self.setAttribute(Qt.WA_NoSystemBackground, True)
            self.config = AppConfig.load()
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

        def _build(self):
            self.root = QWidget(); self.root.setObjectName("rootPanel"); self.setCentralWidget(self.root)
            outer = QVBoxLayout(self.root); outer.setContentsMargins(28,22,28,20); outer.setSpacing(14)

            self.header_card = QFrame()
            self.header_card.setObjectName("serviceHeader")
            header = QHBoxLayout(self.header_card)
            header.setContentsMargins(20, 12, 20, 12)
            header.setSpacing(16)

            self.police_logo = QLabel()
            self.police_logo.setFixedSize(86, 86)
            self.police_logo.setAlignment(Qt.AlignCenter)
            emblem = _police_emblem_pixmap(78)
            if not emblem.isNull():
                self.police_logo.setPixmap(emblem)
            header.addWidget(self.police_logo)

            titles = QVBoxLayout()
            titles.setSpacing(1)
            self.police_title_label = QLabel("ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ")
            self.police_title_label.setObjectName("serviceKicker")
            self.title_label = QLabel("ΔΙΕΥΘΥΝΣΗ ΑΣΤΥΝΟΜΙΑΣ ΦΛΩΡΙΝΑΣ")
            self.title_label.setObjectName("serviceTitle")
            self.department_label = QLabel("ΤΜΗΜΑ ΔΙΑΒΑΤΗΡΙΑΚΟΥ ΕΛΕΓΧΟΥ ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ")
            self.department_label.setObjectName("serviceDepartment")
            self.subtitle_label = QLabel("ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ")
            self.subtitle_label.setObjectName("appSubtitle")
            for label in (self.police_title_label, self.title_label, self.department_label, self.subtitle_label):
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                titles.addWidget(label)
            header.addLayout(titles, 1)

            self.theme_btn = QToolButton()
            self.theme_btn.setMinimumWidth(108)
            self.theme_btn.setMinimumHeight(34)
            self.theme_btn.clicked.connect(self._toggle_theme)
            header.addWidget(self.theme_btn, 0, Qt.AlignTop)

            self.greece_map = GreeceMapWidget()
            header.addWidget(self.greece_map, 0, Qt.AlignRight | Qt.AlignVCenter)
            outer.addWidget(self.header_card)

            columns = QHBoxLayout(); columns.setSpacing(16)

            self.operator_card = QFrame(); self.operator_card.setObjectName("card")
            left = QVBoxLayout(self.operator_card); left.setContentsMargins(20,18,20,18); left.setSpacing(12)
            self.operator_title = QLabel("ΠΡΟΣΩΠΙΚΟ")
            self.operator_title.setAlignment(Qt.AlignCenter); self.operator_title.setStyleSheet("font-size:18px;font-weight:900")
            left.addWidget(self.operator_title)
            operator_form = QFormLayout(); operator_form.setSpacing(12)

            self.agms_input = QLineEdit(); self.agms_input.setPlaceholderText("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.agms_input.setMinimumHeight(42); self.agms_input.textChanged.connect(self._agms_changed)
            self.person_name = QLabel("—"); self.person_name.setWordWrap(True); self.person_name.setStyleSheet("font-size:16px;font-weight:800")
            self.direction = ArrowComboBox(); self.direction.addItems(["ΕΙΣΟΔΟΣ","ΕΞΟΔΟΣ"]); self.direction.setMinimumHeight(42)
            self.position = ArrowComboBox(); self.position.setMinimumHeight(42); self.position.currentTextChanged.connect(self._position_changed)
            operator_form.addRow("Α.Γ.Μ.Σ.", self.agms_input)
            operator_form.addRow("Αστυνομικός", self.person_name)
            operator_form.addRow("ΚΑΤΕΥΘΥΝΣΗ", self.direction)
            operator_form.addRow("ΘΕΣΗ", self.position)
            left.addLayout(operator_form)

            self.active_status = QLabel("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.active_status.setObjectName("statusBox")
            self.active_status.setAlignment(Qt.AlignCenter); self.active_status.setWordWrap(True)
            left.addWidget(self.active_status)
            left.addStretch()

            op_buttons = QHBoxLayout(); op_buttons.setSpacing(12)
            self.start_btn = QPushButton("ΕΝΑΡΞΗ"); self.start_btn.setObjectName("startButton"); self.start_btn.setMinimumHeight(54)
            self.end_btn = QPushButton("ΛΗΞΗ"); self.end_btn.setObjectName("endButton"); self.end_btn.setMinimumHeight(54)
            self.start_btn.clicked.connect(self._start); self.end_btn.clicked.connect(self._end)
            op_buttons.addWidget(self.start_btn); op_buttons.addWidget(self.end_btn)
            left.addLayout(op_buttons)

            self.officer_card = QFrame(); self.officer_card.setObjectName("card")
            right = QVBoxLayout(self.officer_card); right.setContentsMargins(22,18,22,18); right.setSpacing(13)
            self.officer_title = QLabel("ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ")
            self.officer_title.setAlignment(Qt.AlignCenter); self.officer_title.setStyleSheet("font-size:18px;font-weight:900")
            right.addWidget(self.officer_title)

            officer_form = QFormLayout(); officer_form.setSpacing(12)
            self.officer_agms = QLineEdit(); self.officer_agms.setPlaceholderText("Πληκτρολογήστε Α.Γ.Μ.Σ.")
            self.officer_agms.setMinimumHeight(42); self.officer_agms.textChanged.connect(self._officer_changed)
            self.officer_name = QLabel("—"); self.officer_name.setWordWrap(True); self.officer_name.setStyleSheet("font-size:16px;font-weight:800")
            officer_form.addRow("Α.Γ.Μ.Σ.", self.officer_agms)
            officer_form.addRow("Αξιωματικός", self.officer_name)
            right.addLayout(officer_form)

            self.shift_status = QLabel("Δεν υπάρχει ενεργή βάρδια.")
            self.shift_status.setAlignment(Qt.AlignCenter); self.shift_status.setWordWrap(True); self.shift_status.setObjectName("statusBox")
            right.addWidget(self.shift_status)
            right.addStretch()

            shift_buttons = QHBoxLayout(); shift_buttons.setSpacing(12)
            self.start_shift_btn = QPushButton("ΕΝΑΡΞΗ ΒΑΡΔΙΑΣ"); self.start_shift_btn.setObjectName("startButton"); self.start_shift_btn.setMinimumHeight(54)
            self.end_shift_btn = QPushButton("ΛΗΞΗ ΒΑΡΔΙΑΣ"); self.end_shift_btn.setObjectName("endButton"); self.end_shift_btn.setMinimumHeight(54)
            self.start_shift_btn.clicked.connect(self._start_officer_shift_ui)
            self.end_shift_btn.clicked.connect(self._end_officer_shift_ui)
            shift_buttons.addWidget(self.start_shift_btn); shift_buttons.addWidget(self.end_shift_btn)
            right.addLayout(shift_buttons)

            self.comm_status = QLabel("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ — αναμονή σύνδεσης")
            self.comm_status.setObjectName("infoBox")
            self.comm_status.setAlignment(Qt.AlignCenter)
            self.comm_status.setWordWrap(True)
            self.messages_btn = QPushButton("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ")
            self.messages_btn.setObjectName("metalPrimary")
            self.messages_btn.setMinimumHeight(42)
            self.messages_btn.clicked.connect(self._open_messages)
            right.addWidget(self.comm_status)
            right.addWidget(self.messages_btn)
            self.offline_conflicts_btn = QPushButton("ΕΛΕΓΧΟΣ OFFLINE ΑΣΥΜΦΩΝΙΩΝ")
            self.offline_conflicts_btn.setMinimumHeight(38)
            self.offline_conflicts_btn.clicked.connect(self._offline_conflicts_dialog)
            right.addWidget(self.offline_conflicts_btn)

            columns.addWidget(self.operator_card, 1); columns.addWidget(self.officer_card, 1)
            outer.addLayout(columns, 1)

            bottom = QHBoxLayout(); bottom.setSpacing(10)
            self.print_btn = QPushButton("ΤΡΕΧΟΥΣΑ ΑΝΑΦΟΡΑ")
            self.archive_btn = QPushButton("ΑΡΧΕΙΟ ΑΝΑΦΟΡΩΝ")
            self.history_btn = QPushButton("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
            for b in (self.print_btn, self.archive_btn, self.history_btn):
                b.setObjectName("metalPrimary")
                b.setMinimumHeight(44)
                bottom.addWidget(b)
            self.print_btn.clicked.connect(self._report)
            self.archive_btn.clicked.connect(self._report_archive)
            self.history_btn.clicked.connect(self._personnel_history)
            outer.addLayout(bottom)

            bottom2 = QHBoxLayout(); bottom2.setSpacing(10)
            self.active_positions_btn = QPushButton("ΕΝΕΡΓΕΣ ΘΕΣΕΙΣ ΕΡΓΑΣΙΑΣ")
            self.personnel_list_btn = QPushButton("ΕΠΙΛΟΓΗ ΛΙΣΤΑΣ ΠΡΟΣΩΠΙΚΟΥ")
            self.exit_app_btn = QPushButton("ΕΞΟΔΟΣ ΑΠΟ ΤΟ ΠΡΟΓΡΑΜΜΑ")
            self.active_positions_btn.setObjectName("metalPrimary")
            self.personnel_list_btn.setObjectName("metalPrimary")
            self.exit_app_btn.setObjectName("exitButton")
            for b in (self.active_positions_btn, self.personnel_list_btn, self.exit_app_btn):
                b.setMinimumHeight(44)
                bottom2.addWidget(b)
            self.active_positions_btn.clicked.connect(self._live_map)
            self.personnel_list_btn.clicked.connect(self._choose_personnel_list)
            self.exit_app_btn.clicked.connect(self._request_real_exit)
            outer.addLayout(bottom2)

            self.info = QLabel(""); self.info.setObjectName("infoBox"); self.info.setAlignment(Qt.AlignCenter); self.info.setWordWrap(True)
            outer.addWidget(self.info)
        def closeEvent(self, event):
            if self._force_exit:
                event.accept()
                return
            event.ignore()
            self.showMinimized()

        def _cleanup_client(self):
            try:
                self._network_pool.shutdown(wait=False, cancel_futures=True)
                self._position_pool.shutdown(wait=False, cancel_futures=True)
                self._state_pool.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            if self.store:
                try:
                    self.store.remove_client_heartbeat(self.client_id)
                except Exception:
                    pass

        def _end_own_active_positions(self) -> int:
            """Close only START records created by this exact app process."""
            if not self.store:
                return 0
            mine = [
                item for item in self.store.active_all()
                if _clean(item.get("client_id")) == self.client_id
            ]
            for item in mine:
                member = PersonnelRecord(
                    agms=_clean(item.get("agms")),
                    rank=_clean(item.get("rank")),
                    surname=_clean(item.get("surname")),
                    given_name=_clean(item.get("given_name")),
                )
                self.store.end(member, expected_start_event_id=_clean(item.get("event_id")))
            return len(mine)

        def _request_real_exit(self):
            answer = QMessageBox.question(
                self,
                "Έξοδος από το πρόγραμμα",
                "Να κλείσει πραγματικά η εφαρμογή?\\n\\n"
                "Οι ενεργές θέσεις που ανοίχθηκαν από αυτό το παράθυρο "
                "θα λάβουν ΛΗΞΗ πριν κλείσει το πρόγραμμα.\\n"
                "Αν δεν είναι διαθέσιμος ο κεντρικός φάκελος, η έξοδος "
                "δεν θα ολοκληρωθεί με ψευδή επιβεβαίωση.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            try:
                self._end_own_active_positions()
            except Exception as exc:
                QMessageBox.critical(
                    self, "Η λήξη δεν καταχωρίστηκε",
                    f"Δεν επιβεβαιώθηκε η αποδέσμευση της θέσης.\\n{exc}\\n"
                    "Ελέγξτε τον κεντρικό υπολογιστή ή ζητήστε από τον ΑΞΥΠ "
                    "να ολοκληρώσει τη θέση από τη ζωντανή εικόνα."
                )
                return
            self._force_exit = True
            self._cleanup_client()
            QApplication.quit()

        def _sender_payload(self) -> dict:
            officer = self._officer_selected() if hasattr(self, "officer_agms") else None
            if officer:
                return SharedEventStore._person_payload(officer)
            return {
                "computer": socket.gethostname(),
                "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            }

        def _client_worker_labels(self, clients: list[dict]) -> dict[str, str]:
            active_by_computer: dict[str, list[dict]] = {}
            if self.store:
                for item in self.store.active_all():
                    active_by_computer.setdefault(_clean(item.get("computer")).upper(), []).append(item)
            labels = {}
            for client in clients:
                cid = _clean(client.get("client_id"))
                computer = _clean(client.get("computer"))
                user = _clean(client.get("user"))
                people = active_by_computer.get(computer.upper(), [])
                worker_text = ""
                if people:
                    names = []
                    for item in people:
                        name = _clean(
                            f"{item.get('rank','')} {item.get('surname','')} {item.get('given_name','')}"
                        ) or _clean(item.get("full_name"))
                        pos = _clean(item.get("position"))
                        direction = _clean(item.get("direction"))
                        names.append(f"{name} — Θέση {pos} {direction}".strip())
                    worker_text = " | " + " / ".join(names)
                labels[cid] = f"{computer} — {user}{worker_text}"
            return labels

        def _communication_io(self, window_state: str):
            """Shared-folder IO must not run on the Qt GUI thread."""
            session_active = _windows_session_is_active()
            # Central closures are owned only by the offline-sync worker.
            # Running an independent heartbeat-side close here could overtake
            # the original unsent END and discard its timestamp/event ID.
            self.store.write_client_heartbeat(self.client_id, {
                "app_started_at": self._app_started_at,
                "window_state": window_state,
                "windows_session_active": session_active,
            })
            online = self.store.online_clients()
            commands = self.store.pending_commands(self.client_id)
            pending = self.store.pending_messages(self.client_id)
            return online, commands, pending

        def _communication_tick(self):
            if not self.store:
                return
            future = self._communication_future
            if future is not None:
                if not future.done():
                    return
                self._communication_future = None
                try:
                    online, commands, pending = future.result()
                    if hasattr(self, "comm_status"):
                        self.comm_status.setText(
                            f"ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ — ενεργοί σταθμοί: {len(online)}"
                        )
                except Exception:
                    if hasattr(self, "comm_status"):
                        self.comm_status.setText("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ — ΕΛΕΓΧΟΣ ΣΥΝΔΕΣΗΣ")
                    return
                if commands:
                    command = commands[0]
                    if _clean(command.get("type")).upper() == "CLOSE_APP":
                        try:
                            self._end_own_active_positions()
                            self.store.acknowledge_command(
                                _clean(command.get("command_id")), self.client_id
                            )
                        except Exception:
                            if hasattr(self, "comm_status"):
                                self.comm_status.setText(
                                    "ΕΚΚΡΕΜΕΙ ΛΗΞΗ ΘΕΣΗΣ — δεν εκτελέστηκε απομακρυσμένο κλείσιμο"
                                )
                            return
                        self._force_exit = True
                        self._cleanup_client()
                        QApplication.quit()
                        return
                if pending and not self._message_dialog_active:
                    self._show_message_alarm(pending[0])
            if self._communication_future is None:
                state = "ΕΛΑΧΙΣΤΟΠΟΙΗΜΕΝΟ" if self.isMinimized() else "ΑΝΟΙΧΤΟ"
                self._communication_future = self._network_pool.submit(
                    self._communication_io, state
                )

        def _show_message_alarm(self, message: dict):
            if not self.store:
                return
            self._message_dialog_active = True
            try:
                priority = _clean(message.get("priority")).upper() or "ΟΔΗΓΙΑ"
                sender = message.get("sender") or {}
                sender_name = _clean(
                    f"{sender.get('rank','')} {sender.get('surname','')} {sender.get('given_name','')}"
                ) or _clean(sender.get("full_name")) or _clean(sender.get("user")) or "Αξιωματικός Υπηρεσίας"
                created = _clean(message.get("created_at")).replace("T", " ")
                text_value = _clean(message.get("text"))

                self.showNormal()
                self.raise_()
                self.activateWindow()
                if priority in {"ΟΔΗΓΙΑ", "ΕΠΕΙΓΟΝ"}:
                    QApplication.beep()

                box = QMessageBox(self)
                box.setWindowTitle(f"{priority} — ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ")
                box.setIcon(QMessageBox.Warning if priority == "ΕΠΕΙΓΟΝ" else QMessageBox.Information)
                box.setText(
                    f"<b>{priority}</b><br><br>"
                    f"<b>Από:</b> {_escape_html(sender_name)}<br>"
                    f"<b>Ώρα:</b> {_escape_html(created)}<br><br>"
                    f"{_escape_html(text_value)}"
                )
                box.setStandardButtons(QMessageBox.Ok)
                ack_button = box.button(QMessageBox.Ok)
                if ack_button:
                    ack_button.setText("ΕΛΑΒΑ ΓΝΩΣΗ")
                    ack_button.setMinimumWidth(180)
                    ack_button.setMinimumHeight(44)
                box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
                box.exec()
                self.store.acknowledge_message(_clean(message.get("message_id")), self.client_id)
            finally:
                self._message_dialog_active = False

        def _resolve_message_targets(self, selector: str, online: list[dict]) -> list[str]:
            selector = _clean(selector)
            own = self.client_id
            if selector == "ALL":
                return [_clean(x.get("client_id")) for x in online if _clean(x.get("client_id")) != own]
            if selector.startswith("CLIENT:"):
                cid = selector.split(":", 1)[1]
                return [cid] if cid and cid != own else []

            wanted_computers: set[str] = set()
            if self.store:
                for item in self.store.active_all():
                    match = False
                    if selector.startswith("DIR:"):
                        match = _clean(item.get("direction")).upper() == selector.split(":", 1)[1].upper()
                    elif selector.startswith("POS:"):
                        match = _clean(item.get("position")) == selector.split(":", 1)[1]
                    if match:
                        wanted_computers.add(_clean(item.get("computer")).upper())
            return [
                _clean(client.get("client_id"))
                for client in online
                if _clean(client.get("client_id")) != own
                and _clean(client.get("computer")).upper() in wanted_computers
            ]

        def _open_messages(self):
            if not self.store:
                QMessageBox.warning(self, "Μηνύματα", "Δεν είναι διαθέσιμος ο κοινός φάκελος δεδομένων.")
                return
            officer = self._officer_selected()
            if not officer:
                QMessageBox.warning(self, "Μηνύματα", "Πληκτρολογήστε πρώτα έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας.")
                return

            dlg = QDialog(self)
            dlg.setWindowTitle("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ ΑΞΙΩΜΑΤΙΚΟΥ ΥΠΗΡΕΣΙΑΣ")
            dlg.resize(900, 680)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 18, 20, 18)
            lay.setSpacing(10)

            online = self.store.online_clients()
            labels = self._client_worker_labels(online)
            recipient = ArrowComboBox()
            recipient.addItem("ΟΛΟΙ ΟΙ ΕΝΕΡΓΟΙ ΣΤΑΘΜΟΙ", "ALL")
            recipient.addItem("ΟΛΗ Η ΕΙΣΟΔΟΣ", "DIR:ΕΙΣΟΔΟΣ")
            recipient.addItem("ΟΛΗ Η ΕΞΟΔΟΣ", "DIR:ΕΞΟΔΟΣ")
            active_positions = sorted({_clean(x.get("position")) for x in self.store.active_all() if _clean(x.get("position"))})
            for pos in active_positions:
                recipient.addItem(f"ΘΕΣΗ {pos}", f"POS:{pos}")
            for client in online:
                cid = _clean(client.get("client_id"))
                if cid and cid != self.client_id:
                    recipient.addItem(labels.get(cid, cid), f"CLIENT:{cid}")

            priority = ArrowComboBox()
            priority.addItems(["ΟΔΗΓΙΑ", "ΕΠΕΙΓΟΝ", "ΕΝΗΜΕΡΩΣΗ"])
            editor = QPlainTextEdit()
            editor.setPlaceholderText("Γράψτε τι πρέπει να γνωρίζουν ή να κάνουν οι παραλήπτες...")
            editor.setMaximumHeight(130)

            form = QFormLayout()
            form.addRow("Παραλήπτες", recipient)
            form.addRow("Τύπος", priority)
            form.addRow("Μήνυμα / οδηγία", editor)
            lay.addLayout(form)

            send_btn = QPushButton("ΑΠΟΣΤΟΛΗ")
            send_btn.setMinimumHeight(44)
            lay.addWidget(send_btn)

            online_label = QLabel(f"Ενεργοί σταθμοί αυτή τη στιγμή: {len(online)}")
            lay.addWidget(online_label)
            sent_list = QListWidget()
            lay.addWidget(sent_list, 1)

            def refresh_sent():
                sent_list.clear()
                for msg in self.store.recent_sent_messages(20):
                    targets = [_clean(x) for x in msg.get("targets", []) if _clean(x)]
                    acks = msg.get("acknowledgements", [])
                    created = _clean(msg.get("created_at")).replace("T", " ")
                    target_label = _clean(msg.get("target_label")) or "—"
                    body = _clean(msg.get("text"))
                    if len(body) > 90:
                        body = body[:87] + "..."
                    sent_list.addItem(
                        f"{created} | {msg.get('priority','')} | {target_label} | "
                        f"ΕΛΑΒΑΝ {len(acks)}/{len(targets)} | {body}"
                    )

            def do_send():
                target_ids = self._resolve_message_targets(_clean(recipient.currentData()), online)
                try:
                    self.store.send_message(
                        SharedEventStore._person_payload(officer),
                        target_ids,
                        editor.toPlainText(),
                        priority.currentText(),
                        recipient.currentText(),
                    )
                    editor.clear()
                    refresh_sent()
                except Exception as exc:
                    QMessageBox.warning(dlg, "Αποστολή", str(exc))

            send_btn.clicked.connect(do_send)
            refresh_sent()
            dlg.exec()

        def _close_remaining_clients_dialog(self):
            if not self.store:
                return
            clients = [
                c for c in self.store.online_clients()
                if _clean(c.get("client_id")) and _clean(c.get("client_id")) != self.client_id
            ]
            if not clients:
                QMessageBox.information(self, "Τερματικά", "Δεν υπάρχουν άλλα ενεργά τερματικά.")
                return

            labels = self._client_worker_labels(clients)
            dlg = QDialog(self)
            dlg.setWindowTitle("ΕΝΕΡΓΑ ΤΕΡΜΑΤΙΚΑ ΜΕΤΑ ΤΗ ΛΗΞΗ ΒΑΡΔΙΑΣ")
            dlg.resize(820, 520)
            lay = QVBoxLayout(dlg)
            title = QLabel(
                "Οι παρακάτω εφαρμογές παραμένουν ανοικτές.\n"
                "Επιλέξτε ποιες θέλετε να κλείσετε ή κλείστε τες όλες."
            )
            title.setWordWrap(True)
            lay.addWidget(title)
            listing = QListWidget()
            for client in clients:
                cid = _clean(client.get("client_id"))
                item = QListWidgetItem(labels.get(cid, cid))
                item.setData(Qt.UserRole, cid)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                listing.addItem(item)
            lay.addWidget(listing, 1)

            buttons = QHBoxLayout()
            selected_btn = QPushButton("ΚΛΕΙΣΕ ΕΠΙΛΕΓΜΕΝΟΥΣ")
            all_btn = QPushButton("ΚΛΕΙΣΕ ΟΛΟΥΣ")
            leave_btn = QPushButton("ΑΣΤΑ ΑΝΟΙΧΤΑ")
            buttons.addWidget(selected_btn)
            buttons.addWidget(all_btn)
            buttons.addStretch()
            buttons.addWidget(leave_btn)
            lay.addLayout(buttons)

            def send_to(ids: list[str]):
                ids = [x for x in ids if x]
                if not ids:
                    QMessageBox.warning(dlg, "Τερματικά", "Δεν έχει επιλεγεί κανένα τερματικό.")
                    return
                sender = self._sender_payload()
                for cid in ids:
                    self.store.send_close_command(sender, cid, "Λήξη βάρδιας από Αξιωματικό Υπηρεσίας")
                QMessageBox.information(
                    dlg,
                    "Τερματικά",
                    f"Εστάλη εντολή κλεισίματος σε {len(ids)} τερματικά. "
                    "Θα κλείσουν μόλις παραλάβουν την εντολή."
                )
                dlg.accept()

            def close_selected():
                ids = []
                for i in range(listing.count()):
                    item = listing.item(i)
                    if item.checkState() == Qt.Checked:
                        ids.append(_clean(item.data(Qt.UserRole)))
                send_to(ids)

            selected_btn.clicked.connect(close_selected)
            all_btn.clicked.connect(lambda: send_to([_clean(x.get("client_id")) for x in clients]))
            leave_btn.clicked.connect(dlg.reject)
            dlg.exec()

        def _toggle_theme(self):
            self.config.theme = "light" if _clean(self.config.theme).lower() == "dark" else "dark"
            self.config.save()
            self._apply_theme()

        def _apply_theme(self):
            dark = _clean(self.config.theme).lower() == "dark"
            t = THEME_DARK if dark else THEME_LIGHT

            with coherent_widget_update(self):
                palette = self.palette()
                palette.setColor(QPalette.Window, QColor(t["window"]))
                self.setPalette(palette)
                self.setAutoFillBackground(True)

                root_palette = self.root.palette()
                root_palette.setColor(QPalette.Window, QColor(t["window"]))
                self.root.setPalette(root_palette)
                self.root.setAutoFillBackground(True)

                self.setStyleSheet(_theme_stylesheet(self.config.theme))
                self.theme_btn.setText("☀ ΦΩΤΕΙΝΟ" if dark else "☾ ΣΚΟΤΕΙΝΟ")
                if hasattr(self, "greece_map"):
                    self.greece_map.set_dark(dark)
                self._agms_changed()
                self._officer_changed()

        def _find_personnel_file(self) -> Path | None:
            candidates = []
            # Cached roster first, so a powered-off shared host never blocks
            # the operator window during Windows account login.
            cache = _local_root() / "roster"
            for name in ("ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"):
                candidates.append(cache / name)
            legacy = Path(self.config.personnel_file) if _clean(self.config.personnel_file) else None
            if legacy:
                candidates.append(legacy)
            for base in (_app_dir() / "CONFIG", _app_dir(), Path(self.config.central_root)):
                for name in ("ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"):
                    candidates.append(base / name)
            for path in candidates:
                if path.is_file():
                    return path
            return None

        def _apply_config(self):
            self.position.clear(); self.position.addItems(self.config.positions or [])
            self._position_changed(self.position.currentText())
            if not self.config.central_root:
                self.config.central_root = str(_app_dir() / ".tde_runtime")
            # Never touch a possibly disconnected UNC path on the GUI thread.
            self.store = None
            try:
                self.offline.auto_close_previous_windows_users(
                    socket.gethostname(), os.environ.get("USERNAME") or os.environ.get("USER") or "")
            except Exception as exc:
                self._handoff_initial_error = str(exc)
            if getattr(sys, "frozen", False) and not self.config.shared_exe_path:
                self.config.shared_exe_path = str(Path(sys.executable).resolve())
            personnel = self._find_personnel_file()
            if personnel:
                try:
                    self._load_people(str(personnel))
                    if not self.config.personnel_file:
                        self.config.personnel_file = str(personnel)
                except Exception as exc:
                    self.info.setText(f"Πρόβλημα προσωπικού: {exc}")
            self.config.save()
            self._refresh_info(); self._agms_changed(); self._refresh_shift_status()

        def _refresh_info(self):
            if self._handoff_initial_error:
                self.info.setText(
                    "ΕΚΚΡΕΜΕΙ Η ΑΛΛΑΓΗ ΧΡΗΣΤΗ WINDOWS — " + self._handoff_initial_error
                )
                return
            if not self.store:
                self.info.setText("ΧΩΡΙΣ ΚΕΝΤΡΙΚΟ — τοπικές εκκρεμείς εγγραφές, θα γίνει συγχρονισμός μόλις επιστρέψει η σύνδεση.")
            elif self.offline.conflicts():
                self.info.setText("ΑΣΥΜΦΩΝΙΑ ΣΥΓΧΡΟΝΙΣΜΟΥ — απαιτείται έλεγχος ΑΞΥΠ.")
            elif self.offline.pending_count():
                self.info.setText(f"ΑΝΑΜΟΝΗ ΣΥΓΧΡΟΝΙΣΜΟΥ: {self.offline.pending_count()} καταχωρίσεις.")
            elif self.store and self.people:
                self.info.setText(f"Σύστημα έτοιμο — Λίστα προσωπικού: {len(self.people)} άτομα")
            else:
                self.info.setText("Δεν έχει επιλεγεί λίστα προσωπικού.")

        def _save_config(self):
            self.config.positions = [self.position.itemText(i) for i in range(self.position.count()) if _clean(self.position.itemText(i))]
            self.config.save(); self._refresh_info()

        def _load_people(self, path: str):
            self.people = PersonnelRepository.load(path)
            self._people_by_agms = {_clean(p.agms): p for p in self.people}
            try:
                cached = _local_root() / "roster" / Path(path).name
                cached.parent.mkdir(parents=True, exist_ok=True)
                if Path(path).resolve() != cached.resolve():
                    shutil.copy2(path, cached)
            except OSError:
                pass
            self._agms_changed(); self._officer_changed()

        def _choose_personnel_list(self):
            start_dir = str(Path(self.config.personnel_file).parent) if _clean(self.config.personnel_file) else str(_app_dir())
            path, _ = QFileDialog.getOpenFileName(self, "Επιλογή λίστας προσωπικού", start_dir, "Excel (*.xlsx *.xlsm)")
            if not path:
                return
            try:
                self._load_people(path)
                self.config.personnel_file = path
                self.config.save()
                if self.store:
                    self.store.log_admin_action("PERSONNEL_LIST_SELECTED", {"file": path, "people": len(self.people)})
                self._refresh_info()
                QMessageBox.information(self, "Λίστα προσωπικού", f"Επιλέχθηκε λίστα με {len(self.people)} άτομα.\nΘα χρησιμοποιείται αυτόματα στις επόμενες εκκινήσεις.")
            except Exception as exc:
                QMessageBox.critical(self, "Λίστα προσωπικού", f"Δεν ήταν δυνατή η ανάγνωση του αρχείου.\n{exc}")

        def _selected(self) -> PersonnelRecord | None:
            return self._people_by_agms.get(_clean(self.agms_input.text()))

        def _officer_selected(self) -> PersonnelRecord | None:
            return self._people_by_agms.get(_clean(self.officer_agms.text()))

        def _officer_changed(self, *_):
            p = self._officer_selected()
            self.officer_name.setText(_clean(f"{p.rank} {p.surname} {p.given_name}") if p else "—")
            self._refresh_shift_status()

        def _agms_changed(self, *_):
            self._agms_query_serial = getattr(self, "_agms_query_serial", 0) + 1
            serial = self._agms_query_serial
            person = self._selected()
            self.start_btn.setEnabled(False)
            self.end_btn.setEnabled(False)
            if not person:
                self.person_name.setText("—")
                self.active_status.setText(
                    "Ο Α.Γ.Μ.Σ. δεν βρέθηκε στο προσωπικό"
                    if _clean(self.agms_input.text()) else "Πληκτρολογήστε Α.Γ.Μ.Σ."
                )
                return
            self.person_name.setText(_clean(f"{person.rank} {person.surname} {person.given_name}"))
            if self._position_operation_future is not None:
                self.active_status.setText("ΚΑΤΑΧΩΡΙΣΗ ΣΕ ΕΞΕΛΙΞΗ — μην την επαναλάβετε.")
                return
            local = self.offline.local_active(person.agms)
            if self.offline.conflicts():
                self.active_status.setText("ΑΣΥΜΦΩΝΙΑ ΣΥΓΧΡΟΝΙΣΜΟΥ — ΕΝΗΜΕΡΩΣΤΕ ΤΟΝ ΑΞΥΠ")
                return
            if not self.store or self.offline.pending_count():
                self.active_status.setText(
                    (f"ΤΟΠΙΚΗ ΘΕΣΗ {local.get('position','')} — ΕΚΚΡΕΜΕΙ ΚΕΝΤΡΙΚΗ ΕΠΙΒΕΒΑΙΩΣΗ"
                     if local else "ΕΚΤΟΣ ΣΥΝΔΕΣΗΣ — νέα έναρξη θα παραμείνει ΠΡΟΣΩΡΙΝΗ")
                )
                self.end_btn.setEnabled(bool(local))
                self.start_btn.setEnabled(not bool(local))
                return
            self.active_status.setText("ΕΛΕΓΧΟΣ ΕΝΕΡΓΗΣ ΘΕΣΗΣ — αναμονή κεντρικού.")
            def load_remote():
                record = self.store.get_active(person.agms)
                self.offline.remember(person.agms, record)
                return record
            future = self._state_pool.submit(load_remote)
            query_started = time.monotonic()

            def poll():
                if serial != self._agms_query_serial:
                    return
                if not future.done():
                    if time.monotonic() - query_started > 3.0:
                        local = self.offline.local_active(person.agms)
                        self.active_status.setText("ΔΙΚΤΥΟ ΧΩΡΙΣ ΑΠΟΚΡΙΣΗ — τοπική λειτουργία με εκκρεμή επιβεβαίωση")
                        self.start_btn.setEnabled(not bool(local))
                        self.end_btn.setEnabled(bool(local))
                        return
                    QTimer.singleShot(200, poll)
                    return
                try:
                    active = future.result()
                except Exception:
                    local = self.offline.local_active(person.agms)
                    self.active_status.setText("ΧΩΡΙΣ ΣΥΝΔΕΣΗ — τοπικές εγγραφές ΕΚΚΡΕΜΟΥΝ")
                    self.start_btn.setEnabled(not bool(local))
                    self.end_btn.setEnabled(bool(local))
                    return
                if self._position_operation_future is not None:
                    return
                if active:
                    ts = _clean(active.get("timestamp", "")).replace("T", " ")
                    self.active_status.setText(
                        f"ΕΝΕΡΓΗ: ΘΕΣΗ {active.get('position','')} — "
                        f"{active.get('direction','')} — από {ts}"
                    )
                    self.end_btn.setEnabled(True)
                else:
                    self.active_status.setText("Δεν υπάρχει ανοικτή καταχώριση")
                    self.start_btn.setEnabled(True)

            QTimer.singleShot(100, poll)

        @staticmethod
        def _suggested_direction(position: str) -> str:
            pos = _clean(position)
            if pos.isdigit():
                n = int(pos)
                if 1 <= n <= 7: return "ΕΙΣΟΔΟΣ"
                if 8 <= n <= 14: return "ΕΞΟΔΟΣ"
            return "ΕΙΣΟΔΟΣ"

        def _position_changed(self, position: str):
            suggested = self._suggested_direction(position)
            idx = self.direction.findText(suggested)
            if idx >= 0: self.direction.setCurrentIndex(idx)

        def _offline_conflicts_dialog(self):
            officer = self._officer_selected()
            if not officer:
                QMessageBox.warning(self, "ΑΞΥΠ", "Συμπληρώστε πρώτα έγκυρο ΑΓΜΣ ΑΞΥΠ.")
                return
            conflicts = self.offline.conflicts()
            if not conflicts:
                QMessageBox.information(self, "Offline", "Δεν υπάρχουν εκκρεμείς ασυμφωνίες.")
                return
            dlg = QDialog(self)
            dlg.setWindowTitle("ΑΞΥΠ — ΑΣΥΜΦΩΝΙΕΣ ΣΥΓΧΡΟΝΙΣΜΟΥ")
            dlg.resize(820, 520)
            lay = QVBoxLayout(dlg)
            label = QLabel("Η παρακάτω τοπική εγγραφή ΔΕΝ καταχωρίστηκε κεντρικά. "
                           "Ελέγξτε την πραγματική εργασία πριν απορρίψετε την εγγραφή.")
            label.setWordWrap(True)
            lay.addWidget(label)
            listing = QListWidget()
            for rec in conflicts:
                listing.addItem(f"{rec['created_at']} | ΑΓΜΣ {rec['agms']} | "
                                f"{rec['kind']} | ΘΕΣΗ {rec['position']} | {rec['error']}")
                listing.item(listing.count()-1).setData(Qt.UserRole, rec['id'])
            lay.addWidget(listing, 1)
            row = QHBoxLayout()
            reject = QPushButton("ΑΠΟΡΡΙΨΗ ΜΕ ΑΙΤΙΟΛΟΓΙΑ")
            close = QPushButton("ΚΛΕΙΣΙΜΟ")
            row.addWidget(reject); row.addWidget(close); lay.addLayout(row)
            def resolve():
                item = listing.currentItem()
                if not item:
                    return
                reason, ok = QInputDialog.getText(dlg, "Αιτιολογία", "Γιατί απορρίπτεται η τοπική εγγραφή;")
                if not ok: return
                if QMessageBox.question(dlg, "ΕΠΙΒΕΒΑΙΩΣΗ",
                    "Η καταχώριση δεν θα μεταφερθεί κεντρικά. Διατηρείται στο ιστορικό. Συνέχεια;",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                try:
                    self.offline.resolve_conflict(_clean(item.data(Qt.UserRole)), officer.agms, reason)
                    dlg.accept()
                    self._refresh_info()
                    self._agms_changed()
                except Exception as exc:
                    QMessageBox.critical(dlg, "Ασυμφωνία", str(exc))
            reject.clicked.connect(resolve)
            close.clicked.connect(dlg.reject)
            dlg.exec()

        def _offline_tick(self):
            if self._offline_future is not None:
                if not self._offline_future.done():
                    return
                future = self._offline_future
                self._offline_future = None
                try:
                    connected, result = future.result()
                    self.store = connected
                    self._handoff_initial_error = ""
                    if result.get("conflicts"):
                        self.info.setText("ΑΣΥΜΦΩΝΙΑ ΑΠΟΣΥΝΔΕΔΕΜΕΝΩΝ ΚΑΤΑΧΩΡΙΣΕΩΝ — έλεγχος ΑΞΥΠ")
                    self._refresh_info()
                except Exception as exc:
                    self.store = None
                    self._refresh_info()
                    self.info.setText(
                        "ΔΕΝ ΟΛΟΚΛΗΡΩΘΗΚΕ Ο ΣΥΓΧΡΟΝΙΣΜΟΣ / HANDOFF: "
                        + str(exc)[:220]
                        + " — οι εκκρεμείς εγγραφές παραμένουν αποθηκευμένες."
                    )
                self._agms_changed()
            if self._offline_future is not None:
                return
            if not self.config.central_root:
                return
            def work():
                if not Path(self.config.central_root).is_dir():
                    raise BusyError("Ο κεντρικός φάκελος δεν είναι διαθέσιμος.")
                store = SharedEventStore(self.config.central_root)
                report = reconcile_handoff_before_replay(
                    store, self.offline, PersonnelRecord, socket.gethostname(),
                    os.environ.get("USERNAME") or os.environ.get("USER") or "",
                )
                if self.config.shared_exe_path and time.monotonic() - self._last_bootstrap_check > 300:
                    self._last_bootstrap_check = time.monotonic()
                    try:
                        cache_windows_client(_local_root(), self.config.shared_exe_path)
                    except Exception:
                        pass  # cache update must not block shifts
                return store, report
            self._offline_future = self._network_pool.submit(work)

        def _position_action(self, kind: str, person: PersonnelRecord, position: str = "", direction: str = ""):
            if self._handoff_initial_error:
                QMessageBox.warning(
                    self, "ΑΝΑΜΟΝΗ ΣΥΜΦΩΝΙΑΣ WINDOWS",
                    "Δεν επιβεβαιώθηκε η λήξη του προηγούμενου χρήστη. "
                    + self._handoff_initial_error,
                )
                return
            if self._position_operation_future is not None:
                QMessageBox.warning(self, "Καταχώριση", "Υπάρχει ήδη εντολή σε εξέλιξη.")
                return
            self.start_btn.setEnabled(False)
            self.end_btn.setEnabled(False)
            self.active_status.setText("ΤΟΠΙΚΗ ΑΠΟΘΗΚΕΥΣΗ ΚΑΤΑΧΩΡΙΣΗΣ…")
            def work():
                # Never wait on a sleeping/disconnected SMB host while a booth
                # action is being recorded. Store the operation locally first;
                # a separate network worker performs idempotent central replay.
                result = self.offline.enqueue(kind, person, position, direction, self.client_id)
                result["pending_sync"] = True
                result["conflict"] = bool(self.offline.conflicts())
                return result
            future = self._position_pool.submit(work)
            self._position_operation_future = future
            def poll():
                if not future.done():
                    QTimer.singleShot(200, poll)
                    return
                self._position_operation_future = None
                try:
                    outcome = future.result()
                except Exception as exc:
                    QMessageBox.critical(self, "Δεν καταχωρίστηκε", str(exc))
                else:
                    if outcome.get("conflict"):
                        QMessageBox.warning(self, "ΑΣΥΜΦΩΝΙΑ", "Απαιτείται έλεγχος ΑΞΥΠ. Η τοπική εγγραφή δεν διαγράφηκε.")
                    elif outcome["pending_sync"]:
                        QMessageBox.warning(self, "ΕΚΚΡΕΜΕΙ ΣΥΓΧΡΟΝΙΣΜΟΣ", "Η καταχώριση φυλάχθηκε ΤΟΠΙΚΑ. Δεν έχει ακόμη επιβεβαιωθεί κεντρικά.")
                    else:
                        QMessageBox.information(self, "Καταχώριση", f"{kind}: Η καταχώριση επιβεβαιώθηκε κεντρικά.")
                self._refresh_info()
                self._agms_changed()
                # Launch central reconciliation asynchronously; the button
                # remains responsive regardless of central SMB availability.
                self._offline_tick()
            QTimer.singleShot(100, poll)

        def _start(self):
            person = self._selected()
            if not person:
                QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού.")
                return
            position = _clean(self.position.currentText())
            direction = _clean(self.direction.currentText()).upper()
            if position not in {str(i) for i in range(1, 15)}:
                QMessageBox.warning(self, "Θέση", "Επιλέξτε θέση 1 έως 14.")
                return
            self._position_action("START", person, position, direction)

        def _end(self):
            person = self._selected()
            if not person:
                QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού.")
                return
            self._position_action("END", person)

        def _preview_list_dialog(self, title: str, intro: str, agms_list: list[str], allow_exclude: bool) -> tuple[bool,list[str],list[str]]:
            dlg=QDialog(self); dlg.setWindowTitle(title); dlg.resize(620,480)
            lay=QVBoxLayout(dlg); lay.setContentsMargins(20,18,20,18); lay.setSpacing(10)
            heading=QLabel(title); heading.setStyleSheet("font-size:18px;font-weight:900")
            text_label=QLabel(intro); text_label.setWordWrap(True)
            lay.addWidget(heading); lay.addWidget(text_label)
            listing=QListWidget()
            for agms in agms_list:
                p=self._people_by_agms.get(_clean(agms))
                name=_clean(f"{p.rank} {p.surname} {p.given_name}") if p else f"ΑΓΜΣ {agms}"
                item=QListWidgetItem(f"{agms} — {name}")
                item.setData(Qt.UserRole,_clean(agms))
                if allow_exclude:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Checked)
                listing.addItem(item)
            lay.addWidget(listing,1)
            buttons=QHBoxLayout(); cancel=QPushButton("ΑΚΥΡΩΣΗ"); confirm=QPushButton("ΕΠΙΒΕΒΑΙΩΣΗ")
            cancel.clicked.connect(dlg.reject); confirm.clicked.connect(dlg.accept)
            buttons.addStretch(); buttons.addWidget(cancel); buttons.addWidget(confirm); lay.addLayout(buttons)
            if dlg.exec()!=QDialog.Accepted:
                return False,[],[]
            approved=[]; excluded=[]
            for i in range(listing.count()):
                item=listing.item(i); agms=_clean(item.data(Qt.UserRole))
                if allow_exclude and item.checkState()!=Qt.Checked: excluded.append(agms)
                else: approved.append(agms)
            return True,approved,excluded

        def _start_officer_shift_ui(self):
            if not self.store:
                QMessageBox.warning(self,"Έλεγχος","Δεν είναι διαθέσιμος ο φάκελος δεδομένων."); return
            p=self._officer_selected()
            if not p:
                QMessageBox.warning(self,"Έλεγχος","Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
            if self.store.current_shift():
                QMessageBox.warning(self,"Βάρδια","Υπάρχει ήδη ενεργή βάρδια."); return
            active=self.store.active_all()
            agms=[]
            for item in active:
                a=_clean(item.get("agms"))
                if a and a not in agms: agms.append(a)
            ok,approved,excluded=self._preview_list_dialog(
                "ΠΡΟΕΠΙΣΚΟΠΗΣΗ ΕΝΑΡΞΗΣ ΒΑΡΔΙΑΣ",
                "Ελέγξτε το προσωπικό που βρίσκεται ήδη σε ενεργή θέση. Αποεπιλέξτε όποιον δεν πρέπει να συμπεριληφθεί στη νέα βάρδια.",
                agms, True
            )
            if not ok: return
            try:
                shift=self.store.start_officer_shift(p,initial_approved=approved,initial_excluded=excluded)
                self._last_shift_signature=""
                self._refresh_shift_status()
                QMessageBox.information(self,"Βάρδια",f"Η βάρδια ξεκίνησε στις {shift['start_at'].replace('T',' ')}.")
            except Exception as exc:
                QMessageBox.critical(self,"Βάρδια",str(exc))

        def _resolve_pending_members(self) -> bool:
            if not self.store or self._pending_prompt_active:
                return False
            shift=self.store.sync_active_shift()
            pending=list(shift.get("pending",[])) if shift else []
            if not pending:
                return True
            self._pending_prompt_active=True
            try:
                for agms in pending:
                    p=self._people_by_agms.get(_clean(agms))
                    name=_clean(f"{p.rank} {p.surname} {p.given_name}") if p else f"ΑΓΜΣ {agms}"
                    answer=QMessageBox.question(
                        self,
                        "Νέο άτομο στη βάρδια",
                        f"{name}\n\nΚαταγράφηκε σε θέση μετά την έναρξη της βάρδιας.\nΝα συμπεριληφθεί στη βάρδια;",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    if answer == QMessageBox.Yes:
                        self.store.set_shift_member_state(agms, "APPROVED")
                    else:
                        confirm_exclusion = QMessageBox.question(
                            self,
                            "Επιβεβαίωση εξαίρεσης",
                            f"{name}\n\nΕίστε βέβαιοι ότι θέλετε να ΕΞΑΙΡΕΣΕΤΕ το άτομο από τη βάρδια;",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if confirm_exclusion == QMessageBox.Yes:
                            self.store.set_shift_member_state(agms, "EXCLUDED")
            finally:
                self._pending_prompt_active=False
            self._refresh_shift_status()
            return True

        def _confirm_and_end_officer_shift(self, officer: PersonnelRecord) -> bool:
            """Per-person END and group END inside shift close; live map unchanged."""
            if not self.store:
                return False
            previous = getattr(self, "_shift_closure_future", None)
            if previous is not None and not previous.done():
                QMessageBox.warning(
                    self, "Εκκρεμής καταχώριση",
                    "Υπάρχει προηγούμενη εντολή λήξης σε εξέλιξη. "
                    "Ελέγξτε ξανά την κατάσταση αφού ολοκληρωθεί.",
                )
                return False

            dlg = QDialog(self)
            dlg.setWindowTitle("ΛΗΞΗ ΒΑΡΔΙΑΣ — ΕΚΚΡΕΜΕΙΣ ΘΕΣΕΙΣ")
            dlg.resize(920, 670)
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(20, 18, 20, 18)
            lay.setSpacing(12)
            heading = QLabel("ΑΣΤΥΝΟΜΙΚΟΙ ΠΟΥ ΔΕΝ ΕΧΟΥΝ ΚΑΝΕΙ ΛΗΞΗ")
            heading.setStyleSheet("font-size:17px;font-weight:800")
            lay.addWidget(heading)
            status = QLabel("Έλεγχος ενεργών θέσεων…")
            status.setWordWrap(True)
            lay.addWidget(status)
            pending_note = QLabel("")
            pending_note.setWordWrap(True)
            lay.addWidget(pending_note)
            positions_list = QListWidget()
            positions_list.setAlternatingRowColors(True)
            lay.addWidget(positions_list, 1)
            excluded_note = QLabel("")
            excluded_note.setWordWrap(True)
            lay.addWidget(excluded_note)
            footer = QHBoxLayout()
            refresh_btn = QPushButton("ΑΝΑΝΕΩΣΗ")
            group_btn = QPushButton("ΟΜΑΔΙΚΗ ΛΗΞΗ")
            finalize_btn = QPushButton("ΟΛΟΚΛΗΡΩΣΗ ΒΑΡΔΙΑΣ")
            cancel_btn = QPushButton("ΚΛΕΙΣΙΜΟ")
            for button in (refresh_btn, group_btn, finalize_btn, cancel_btn):
                button.setMinimumHeight(42)
                footer.addWidget(button)
            lay.addLayout(footer)

            worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="TDE-shift-close")
            state = {"future": None, "kind": "", "shift": None,
                     "active": [], "excluded": [], "row_buttons": [],
                     "finalized": False, "pending": False}

            def full_name(item: dict) -> str:
                name = _clean(
                    f"{item.get('rank', '')} {item.get('surname', '')} {item.get('given_name', '')}"
                )
                return name or _clean(item.get("full_name")) or f"ΑΓΜΣ {_clean(item.get('agms'))}"

            def position_label(item: dict) -> str:
                return (
                    f"{full_name(item)}  |  ΘΕΣΗ {_clean(item.get('position'))}"
                    f" — {_clean(item.get('direction'))}  |  "
                    f"ΕΝΑΡΞΗ {_clean(item.get('timestamp')).replace('T', ' ')}"
                )

            def set_busy(message: str):
                status.setText(message)
                refresh_btn.setEnabled(False)
                group_btn.setEnabled(False)
                finalize_btn.setEnabled(False)
                for button in state["row_buttons"]:
                    button.setEnabled(False)

            def submit(kind: str, task):
                if state["future"] is not None:
                    return
                set_busy("Επικοινωνία με τον κεντρικό φάκελο — αναμονή επιβεβαίωσης…")
                state["kind"] = kind
                future = worker.submit(task)
                state["future"] = future
                if kind in {"single", "finalize"}:
                    self._shift_closure_future = future

            def load_data():
                shift = self.store.sync_active_shift()
                active = self.store.active_all() if shift else []
                return shift, active

            def reload():
                submit("load", load_data)

            def selected_member_end(item: dict):
                if state["future"] is not None:
                    return
                name = full_name(item)
                confirm = QMessageBox.question(
                    dlg, "ΜΕΜΟΝΩΜΕΝΗ ΛΗΞΗ",
                    f"{position_label(item)}\n\n"
                    f"Να καταχωριστεί ΛΗΞΗ μόνο για τον/την {name};\n"
                    "Η βάρδια θα παραμείνει ανοικτή.",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if confirm != QMessageBox.Yes:
                    return
                shift_id = _clean(state["shift"].get("shift_id"))
                agms = _clean(item.get("agms"))
                start_id = _clean(item.get("event_id"))
                submit(
                    "single",
                    lambda: self.store.end_officer_shift_member(
                        officer, agms, shift_id, start_id
                    ),
                )

            def finalize_shift(group: bool):
                if state["future"] is not None or not state["shift"]:
                    return
                pending = bool(state["shift"].get("pending"))
                if pending:
                    QMessageBox.warning(
                        dlg, "Άτομα σε αναμονή",
                        "Υπάρχουν άτομα σε ΑΝΑΜΟΝΗ. "
                        "Ολοκληρώστε πρώτα την ΑΠΟΔΟΧΗ ή ΕΞΑΙΡΕΣΗ από τον πίνακα ΑΞΥΠ.",
                    )
                    return
                items = list(state["active"])
                if not group and items:
                    return
                if group and not items:
                    return
                if group:
                    names = "\n".join(f"• {position_label(x)}" for x in items)
                    question = (
                        "Να καταχωριστεί ΟΜΑΔΙΚΗ ΛΗΞΗ στους παρακάτω αστυνομικούς;\n\n"
                        f"{names}\n\n"
                        "Θα ολοκληρωθεί και η βάρδια. Οι ΕΞΑΙΡΕΜΕΝΟΙ δεν θα επηρεαστούν."
                    )
                else:
                    question = (
                        "Δεν υπάρχουν πλέον ανοικτές θέσεις στους ΑΠΟΔΕΚΤΟΥΣ.\n\n"
                        "Να ολοκληρωθεί η βάρδια;"
                    )
                confirm = QMessageBox.question(
                    dlg, "ΕΠΙΒΕΒΑΙΩΣΗ ΛΗΞΗΣ ΒΑΡΔΙΑΣ", question,
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if confirm != QMessageBox.Yes:
                    return
                shift_id = _clean(state["shift"].get("shift_id"))
                snapshot = {
                    _clean(x.get("agms")): _clean(x.get("event_id"))
                    for x in items
                }
                submit(
                    "finalize",
                    lambda: self.store.end_officer_shift(
                        officer, expected_active_start_ids=snapshot,
                        expected_shift_id=shift_id,
                    ),
                )

            def render(shift: dict | None, active: list[dict]):
                positions_list.clear()
                state["row_buttons"] = []
                state["shift"] = shift
                state["active"] = []
                state["excluded"] = []
                if not shift:
                    status.setText("Δεν υπάρχει ενεργή βάρδια.")
                    pending_note.setText("")
                    excluded_note.setText("")
                    group_btn.setEnabled(False)
                    finalize_btn.setEnabled(False)
                    refresh_btn.setEnabled(True)
                    return
                approved = {_clean(x) for x in shift.get("approved", [])}
                state["active"] = [x for x in active if _clean(x.get("agms")) in approved]
                state["excluded"] = [x for x in active if _clean(x.get("agms")) not in approved]
                state["pending"] = bool(shift.get("pending"))
                if state["pending"]:
                    pending_note.setText(
                        "ΠΡΟΣΟΧΗ: Υπάρχουν αστυνομικοί σε ΑΝΑΜΟΝΗ. "
                        "Αποφασίστε ΑΠΟΔΟΧΗ ή ΕΞΑΙΡΕΣΗ στον πίνακα ΑΞΥΠ "
                        "πριν ολοκληρώσετε τη βάρδια."
                    )
                else:
                    pending_note.setText("")
                for item in state["active"]:
                    row_widget = QWidget()
                    row_lay = QHBoxLayout(row_widget)
                    row_lay.setContentsMargins(8, 4, 8, 4)
                    label = QLabel(position_label(item))
                    label.setWordWrap(True)
                    row_lay.addWidget(label, 1)
                    button = QPushButton("ΛΗΞΗ")
                    button.setMinimumWidth(100)
                    button.setMinimumHeight(38)
                    button.clicked.connect(
                        lambda checked=False, rec=dict(item): selected_member_end(rec)
                    )
                    row_lay.addWidget(button)
                    entry = QListWidgetItem()
                    entry.setSizeHint(row_widget.sizeHint())
                    positions_list.addItem(entry)
                    positions_list.setItemWidget(entry, row_widget)
                    state["row_buttons"].append(button)
                count = len(state["active"])
                status.setText(
                    f"Εκκρεμούν {count} λήξεις για την τρέχουσα βάρδια."
                    if count else "Όλοι οι ΑΠΟΔΕΚΤΟΙ έχουν κάνει ΛΗΞΗ."
                )
                if state["excluded"]:
                    excluded_note.setText(
                        "ΕΞΑΙΡΕΜΕΝΟΙ / ΕΚΤΟΣ ΒΑΡΔΙΑΣ — ΔΕΝ ΘΑ ΚΛΕΙΣΟΥΝ:\n"
                        + "\n".join(position_label(x) for x in state["excluded"])
                    )
                else:
                    excluded_note.setText("")
                enabled = not state["pending"]
                refresh_btn.setEnabled(True)
                group_btn.setEnabled(enabled and count > 0)
                finalize_btn.setEnabled(enabled and count == 0)
                for button in state["row_buttons"]:
                    button.setEnabled(enabled)

            def poll():
                future = state["future"]
                if future is None:
                    return
                if not future.done():
                    return
                kind = state["kind"]
                state["future"] = None
                state["kind"] = ""
                try:
                    output = future.result()
                except Exception as exc:
                    QMessageBox.critical(
                        dlg, "Δεν επιβεβαιώθηκε η καταχώριση",
                        f"{exc}\n\nΕλέγξτε ξανά την κατάσταση πριν επαναλάβετε.",
                    )
                    if kind != "load":
                        reload()
                    else:
                        status.setText("Δεν είναι διαθέσιμα τα κεντρικά δεδομένα.")
                        refresh_btn.setEnabled(True)
                    return
                if kind == "load":
                    render(*output)
                elif kind == "single":
                    reload()
                elif kind == "finalize":
                    state["finalized"] = True
                    self._refresh_shift_status()
                    QMessageBox.information(
                        dlg, "Η ΒΑΡΔΙΑ ΟΛΟΚΛΗΡΩΘΗΚΕ",
                        "Η βάρδια οριστικοποιήθηκε και αποθηκεύτηκε.\n"
                        f"Αυτόματες λήξεις με την ολοκλήρωση: "
                        f"{len(output.get('closed_active_agms', []))}.",
                    )
                    dlg.accept()

            refresh_btn.clicked.connect(reload)
            group_btn.clicked.connect(lambda: finalize_shift(True))
            finalize_btn.clicked.connect(lambda: finalize_shift(False))
            cancel_btn.clicked.connect(dlg.reject)
            timer = QTimer(dlg)
            timer.timeout.connect(poll)
            timer.start(180)
            reload()
            try:
                dlg.exec()
            finally:
                timer.stop()
                worker.shutdown(wait=False, cancel_futures=True)
            return bool(state["finalized"])

        def _end_officer_shift_ui(self):
            if not self.store:
                return
            officer = self._officer_selected()
            if not officer:
                QMessageBox.warning(
                    self, "Έλεγχος",
                    "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."
                )
                return
            try:
                self._confirm_and_end_officer_shift(officer)
            except Exception as exc:
                QMessageBox.critical(self, "Λήξη βάρδιας", str(exc))

        def _refresh_shift_status(self):
            if not hasattr(self, "shift_status"):
                return
            if not self.store:
                self.shift_status.setText("ΑΝΑΜΟΝΗ ΣΥΝΔΕΣΗΣ ΜΕ ΤΑ ΚΕΝΤΡΙΚΑ ΔΕΔΟΜΕΝΑ")
                self.start_shift_btn.setEnabled(False)
                self.end_shift_btn.setEnabled(False)
                return
            previous = getattr(self, "_shift_status_future", None)
            if previous is not None and not previous.done():
                return
            self.start_shift_btn.setEnabled(False)
            self.end_shift_btn.setEnabled(False)

            def read_status():
                shift = self.store.current_shift()
                final = None if shift else self.store.current_report_shift()
                return shift, final

            future = self._state_pool.submit(read_status)
            self._shift_status_future = future

            def poll():
                if self._shift_status_future is not future:
                    return
                if not future.done():
                    QTimer.singleShot(200, poll)
                    return
                self._shift_status_future = None
                try:
                    shift, report_shift = future.result()
                except Exception:
                    self.shift_status.setText(
                        "ΑΝΑΜΟΝΗ ΣΥΝΔΕΣΗΣ ΜΕ ΤΑ ΚΕΝΤΡΙΚΑ ΔΕΔΟΜΕΝΑ"
                    )
                    self.start_shift_btn.setEnabled(False)
                    self.end_shift_btn.setEnabled(False)
                    return
                officer = self._officer_selected()
                if not shift:
                    if report_shift and _clean(report_shift.get("status")).upper() == "FINALIZED":
                        ended = _clean(report_shift.get("end_at"))
                        try:
                            ended_dt = datetime.fromisoformat(ended)
                            ended_text = f"{ended_dt:%d/%m/%Y %H:%M}"
                        except Exception:
                            ended_text = ended.replace("T", " ") if ended else "—"
                        self.shift_status.setText(
                            f"Η προηγούμενη βάρδια έληξε {ended_text}.\\n"
                            "Η αναφορά της παραμένει ΤΡΕΧΟΥΣΑ μέχρι την έναρξη της επόμενης."
                        )
                    else:
                        self.shift_status.setText("Δεν υπάρχει ενεργή βάρδια.")
                    self.start_shift_btn.setEnabled(bool(officer))
                    self.end_shift_btn.setEnabled(False)
                    return
                started = datetime.fromisoformat(shift["start_at"])
                starter = shift.get("start_officer") or {}
                name = _clean(f"{starter.get('rank','')} {starter.get('full_name','')}")
                pending = len(shift.get("pending", []))
                msg = f"Ενεργή βάρδια από {started:%d/%m/%Y %H:%M}\\n{name}"
                if pending:
                    msg += f"\\nΑναμονή επιβεβαίωσης: {pending}"
                self.shift_status.setText(msg)
                self.start_shift_btn.setEnabled(False)
                self.end_shift_btn.setEnabled(bool(officer))

            QTimer.singleShot(100, poll)

        def _check_shift_updates(self):
            if not self.store:
                return
            future = self._shift_future
            if future is None:
                self._shift_future = self._network_pool.submit(self.store.sync_active_shift)
                return
            if not future.done():
                return
            self._shift_future = None
            try:
                shift = future.result()
            except Exception:
                if hasattr(self, "shift_status"):
                    self.shift_status.setText("ΑΝΑΜΟΝΗ ΣΥΝΔΕΣΗΣ ΜΕ ΚΕΝΤΡΙΚΑ ΔΕΔΟΜΕΝΑ")
                return
            if not shift:
                if self._last_shift_signature != "NO_SHIFT":
                    self._last_shift_signature = "NO_SHIFT"
                    self._refresh_shift_status()
                return
            signature = json.dumps({
                "approved": shift.get("approved", []),
                "excluded": shift.get("excluded", []),
                "pending": shift.get("pending", [])
            }, ensure_ascii=False, sort_keys=True)
            if signature != self._last_shift_signature:
                self._last_shift_signature = signature
                self._refresh_shift_status()
            if shift.get("pending") and not self._pending_prompt_active:
                self._resolve_pending_members()

        def _live_map(self):
            if not self.store:
                QMessageBox.warning(self,"Έλεγχος","Δεν είναι διαθέσιμος ο φάκελος δεδομένων."); return
            LiveMapDialog(self.store, self._people_by_agms, self._officer_selected, self).exec()

        def _shift_admin(self):
            pass

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

        def _shift_admin(self):
            self._admin()

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
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())

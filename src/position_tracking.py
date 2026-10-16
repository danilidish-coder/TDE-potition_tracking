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
    from position_tracking_ui_admin import AdministrationMixin
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











    class MainWindow(AdministrationMixin, PersonnelHistoryMixin, ReportDialogsMixin, ShiftControllerMixin, ShiftEndDialogMixin, WindowLifecycleMixin, PositionActionsMixin, PersonnelSelectionMixin, MessageDialogsMixin, CommunicationMixin, ConfigurationMixin, MainViewMixin, QMainWindow):
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

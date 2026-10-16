"""Compose independent views/controllers and initialize the main window state."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from position_tracking_offline import OfflineJournal
from position_tracking_constants import APP_VERSION
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord
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
from position_tracking_ui_assets import _police_emblem_pixmap
from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow


class MainWindow(AdministrationMixin, PersonnelHistoryMixin, ReportDialogsMixin, ShiftControllerMixin, ShiftEndDialogMixin, WindowLifecycleMixin, PositionActionsMixin, PersonnelSelectionMixin, MessageDialogsMixin, CommunicationMixin, ConfigurationMixin, MainViewMixin, QMainWindow):

    def __init__(self, services: WindowServices):
        super().__init__()
        self._services = services
        self.config = self._services.config_type.load()
        self.people: tuple[PersonnelRecord, ...] = ()
        self._people_by_agms: dict[str, PersonnelRecord] = {}
        self.store: SharedEventStore | None = None
        self._pending_prompt_active = False
        self._last_shift_signature = ''
        self._force_exit = False
        self._message_dialog_active = False
        self._app_started_at = datetime.now().isoformat(timespec='seconds')
        self.client_id = SharedEventStore.local_client_id()
        self._network_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='TDE-network')
        self._position_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='TDE-position')
        self._state_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='TDE-state')
        self._position_operation_future = None
        self._last_bootstrap_check = 0.0
        self._offline_future = None
        self._offline_polling = False
        self._pending_central_store = None
        self._handoff_initial_error = ''
        self.offline = OfflineJournal(self._services.machine_queue_root())
        self._agms_query_serial = 0
        self._shift_status_future = None
        self._communication_future = None
        self._shift_future = None
        self.setWindowTitle(f'Τ.Δ.Ε. Κρυσταλλοπηγής - Καταγραφή Θέσεων v{APP_VERSION}')
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

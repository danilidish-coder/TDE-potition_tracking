"""Main window widget layout and coherent application of theme data."""
from __future__ import annotations
from position_tracking_common import _clean
from position_tracking_ui_assets import _police_emblem_pixmap, GreeceMapWidget, ArrowComboBox
from position_tracking_theme import THEME_DARK, THEME_LIGHT, _theme_stylesheet
from position_tracking_rendering import coherent_widget_update
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget, QToolButton


class MainViewMixin:
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


"""Shared look of the central windows: the same theme, header and cards as v1.2.6.

Only presentation. No data access, no settings file: the theme choice lives in
memory for the running window.
"""
from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from position_tracking_theme import THEME_DARK, THEME_LIGHT, _theme_stylesheet
from position_tracking_ui_assets import GreeceMapWidget, _police_emblem_pixmap


def _extra_stylesheet(theme: str) -> str:
    """Tabs, check boxes and scroll areas, which the v1.2.6 theme did not need."""
    t = THEME_DARK if theme == "dark" else THEME_LIGHT
    return f"""
        QTabWidget::pane {{ border:1px solid {t['border']}; border-radius:12px; background:{t['card']}; top:-1px; }}
        QTabBar::tab {{
            background:{t['card2']}; color:{t['muted']}; border:1px solid {t['border']};
            border-bottom:none; border-top-left-radius:10px; border-top-right-radius:10px;
            padding:9px 18px; margin-right:3px; font-weight:800;
        }}
        QTabBar::tab:selected {{ background:{t['card']}; color:{t['text']}; border-bottom:3px solid {t['accent']}; }}
        QTabBar::tab:hover {{ color:{t['text']}; }}
        QTabWidget QWidget#tabPage {{ background:{t['card']}; }}
        QLabel#personName {{ font-size:16px; font-weight:800; }}
        QLabel#cardTitle {{ font-size:18px; font-weight:900; }}
        QLabel#noticeBox {{ color:{t['muted']}; font-size:10pt; }}
    """


def build_header(window, subtitle: str = "ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ") -> QFrame:
    """The service header of v1.2.6: emblem, titles, theme button, Greece map."""
    card = QFrame()
    card.setObjectName("serviceHeader")
    row = QHBoxLayout(card)
    row.setContentsMargins(20, 12, 20, 12)
    row.setSpacing(16)
    logo = QLabel()
    logo.setFixedSize(86, 86)
    logo.setAlignment(Qt.AlignCenter)
    emblem = _police_emblem_pixmap(78)
    if not emblem.isNull():
        logo.setPixmap(emblem)
    row.addWidget(logo)
    titles = QVBoxLayout()
    titles.setSpacing(1)
    for text, name in (("ΕΛΛΗΝΙΚΗ ΑΣΤΥΝΟΜΙΑ", "serviceKicker"),
                       ("ΔΙΕΥΘΥΝΣΗ ΑΣΤΥΝΟΜΙΑΣ ΦΛΩΡΙΝΑΣ", "serviceTitle"),
                       ("ΤΜΗΜΑ ΔΙΑΒΑΤΗΡΙΑΚΟΥ ΕΛΕΓΧΟΥ ΚΡΥΣΤΑΛΛΟΠΗΓΗΣ", "serviceDepartment"),
                       (subtitle, "appSubtitle")):
        label = QLabel(text)
        label.setObjectName(name)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        titles.addWidget(label)
    row.addLayout(titles, 1)
    window.theme_btn = QToolButton()
    window.theme_btn.setMinimumWidth(108)
    window.theme_btn.setMinimumHeight(34)
    window.theme_btn.clicked.connect(lambda: toggle_theme(window))
    row.addWidget(window.theme_btn, 0, Qt.AlignTop)
    window.greece_map = GreeceMapWidget()
    row.addWidget(window.greece_map, 0, Qt.AlignRight | Qt.AlignVCenter)
    return card


def new_card() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    return card


def apply_look(window, root: QWidget, theme: str = "light") -> None:
    """Colour the window exactly like v1.2.6. Safe to call again for a theme switch."""
    theme = "dark" if theme == "dark" else "light"
    window._look_theme = theme
    t = THEME_DARK if theme == "dark" else THEME_LIGHT
    root.setObjectName("rootPanel")
    for widget in (window, root):
        palette = widget.palette()
        palette.setColor(QPalette.Window, QColor(t["window"]))
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)
    window.setStyleSheet(_theme_stylesheet(theme) + _extra_stylesheet(theme))
    button = getattr(window, "theme_btn", None)
    if button is not None:
        button.setText("☀ ΦΩΤΕΙΝΟ" if theme == "dark" else "☾ ΣΚΟΤΕΙΝΟ")


def toggle_theme(window) -> None:
    apply_look(window, window.centralWidget(), "light" if getattr(window, "_look_theme", "light") == "dark" else "dark")

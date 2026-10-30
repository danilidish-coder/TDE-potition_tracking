"""Pure theme palette and stylesheet generation, independent of Qt/startup."""
from position_tracking_common import _clean


THEME_DARK = {
    "window": "#07111f", "panel": "#0d1b2b", "card": "#10243a", "card2": "#132c46",
    "text": "#f4f8ff", "muted": "#93a8bf", "accent": "#1378d4", "accent2": "#0b5ea8",
    "border": "#214565", "danger": "#b73a4a", "ok": "#1f9d70", "input": "#0a1726",
}

THEME_LIGHT = {
    "window": "#eef3f7", "panel": "#f7fafc", "card": "#ffffff", "card2": "#e7eef3",
    "text": "#153247", "muted": "#667b8b", "accent": "#173d5d", "accent2": "#0d2940",
    "border": "#d4e0e8", "danger": "#a93646", "ok": "#177d72", "input": "#ffffff",
}

def _theme_stylesheet(theme: str) -> str:
    dark = _clean(theme).lower() == "dark"
    t = THEME_DARK if dark else THEME_LIGHT
    metal_top = "#294b66" if dark else "#ffffff"
    metal_mid = "#18364f" if dark else "#d9e2e8"
    metal_low = "#10283d" if dark else "#aebdc8"
    metal_edge = "#355d7d" if dark else "#8298a8"
    primary_top = "#3f6d8d" if dark else "#477495"
    primary_mid = "#1b4a6d" if dark else "#173d5d"
    primary_low = "#0b263b" if dark else "#0d2940"
    header_bg = "#0d1b2b" if dark else "#ffffff"
    return f"""
            QMainWindow, QWidget#rootPanel {{ background: {t['window']}; color: {t['text']}; }}
            QWidget {{ color: {t['text']}; font-family:'Segoe UI'; font-size:10.5pt; }}
            QDialog {{ background: {t['window']}; color: {t['text']}; }}
            QDialog QLabel {{ color: {t['text']}; }}

            QFrame#serviceHeader {{
                background:{header_bg};
                border:1px solid {t['border']};
                border-bottom:3px solid {primary_low};
                border-radius:18px;
            }}
            QLabel#serviceKicker {{
                color:{t['accent']}; font-size:11px; font-weight:900; letter-spacing:1px;
            }}
            QLabel#serviceTitle {{
                color:{t['text']}; font-size:19px; font-weight:900;
            }}
            QLabel#serviceDepartment {{
                color:{t['text']}; font-size:14px; font-weight:850;
            }}
            QLabel#appSubtitle {{
                color:{t['muted']}; font-size:11px; font-weight:800; letter-spacing:1px;
            }}

            QFrame#card {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['card2']},stop:0.10 {t['card']},stop:1 {t['card']});
                border:1px solid {t['border']}; border-bottom:3px solid {metal_edge}; border-radius:16px;
            }}
            QLabel#statusBox, QLabel#infoBox {{
                background:{t['card2']}; border:1px solid {t['border']}; border-radius:10px;
                padding:9px; color:{t['muted']}; font-weight:700;
            }}

            QLineEdit, QComboBox, QDateEdit, QDateTimeEdit, QSpinBox, QTimeEdit, QPlainTextEdit {{
                background:{t['input']}; color:{t['text']}; border:2px solid {t['border']};
                border-radius:10px; min-height:36px; padding:4px 9px;
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDateTimeEdit:focus, QSpinBox:focus, QTimeEdit:focus, QPlainTextEdit:focus {{
                border:2px solid {t['accent']}; background:{t['card']};
            }}
            QComboBox {{ padding-right:28px; }}
            QComboBox::drop-down {{
                width:28px; border-left:1px solid {t['border']}; background:{t['card2']};
                border-top-right-radius:8px; border-bottom-right-radius:8px;
            }}
            QComboBox::down-arrow {{ image:none; width:0px; height:0px; }}
            QComboBox QAbstractItemView {{
                background:{t['card2']}; color:{t['text']}; border:2px solid {t['accent']};
                selection-background-color:{t['accent']}; selection-color:white; outline:0; padding:4px;
            }}
            QListWidget, QTableWidget, QTextBrowser {{
                background:{t['input']}; color:{t['text']}; border:2px solid {t['border']};
                border-radius:9px; alternate-background-color:{t['card2']};
                selection-background-color:{t['accent']}; selection-color:white;
            }}
            QListWidget::item {{ padding:6px; }}
            QListWidget::item:selected {{ background:{t['accent']}; color:white; }}
            QHeaderView::section {{
                background:{t['card2']}; color:{t['text']}; border:1px solid {t['border']};
                padding:6px; font-weight:700;
            }}

            QPushButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {metal_top}, stop:0.18 {metal_mid}, stop:0.78 {metal_mid}, stop:1 {metal_low});
                color:{t['text']}; border:1px solid {metal_edge}; border-bottom:4px solid {primary_low};
                border-radius:11px; padding:7px 14px; font-weight:800;
            }}
            QPushButton:hover {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {primary_top}, stop:0.20 {primary_mid}, stop:1 {primary_low});
                color:white; border-color:{primary_top}; border-bottom-color:#081b29;
            }}
            QPushButton:pressed {{
                background:{primary_low}; color:white; border-bottom-width:1px; padding-top:10px;
            }}
            QPushButton:disabled {{
                color:{t['muted']}; background:{t['panel']}; border-color:{t['border']};
            }}

            QPushButton#metalPrimary {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {primary_top}, stop:0.16 {primary_mid}, stop:0.78 {t['accent']}, stop:1 {primary_low});
                color:white; border:1px solid {primary_top}; border-bottom:5px solid #081b29;
                border-radius:12px; font-weight:900;
            }}
            QPushButton#metalPrimary:hover {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #5685a4, stop:0.20 #2a5b7d, stop:1 {primary_low});
            }}
            QPushButton#metalPrimary:pressed {{
                background:{primary_low}; border-bottom-width:1px; padding-top:11px;
            }}

            QPushButton#exitButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 {metal_top}, stop:0.25 {metal_mid}, stop:1 {metal_low});
                color:{t['danger']}; border:1px solid {t['danger']}; border-bottom:4px solid #6f1f2d;
                font-weight:850;
            }}
            QPushButton#exitButton:hover {{ background:{t['danger']}; color:white; }}

            QToolButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {metal_top},stop:1 {metal_low});
                color:{t['text']}; border:1px solid {metal_edge}; border-bottom:3px solid {primary_low};
                border-radius:10px; padding:7px 11px; font-weight:800;
            }}
            QToolButton:hover {{
                background:{t['accent']}; color:white; border-color:{t['accent']};
            }}

            QPushButton#startButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #34a98d,stop:0.18 {t['ok']},stop:1 #0d5f46);
                color:white; border:1px solid #3ab79a; border-bottom:5px solid #084b37;
                font-size:17px; font-weight:900; text-align:center;
            }}
            QPushButton#startButton:pressed {{ border-bottom-width:1px; padding-top:11px; }}
            QPushButton#endButton {{
                background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #cf5b68,stop:0.18 {t['danger']},stop:1 #6f1f2d);
                color:white; border:1px solid #d56a75; border-bottom:5px solid #541722;
                font-size:17px; font-weight:900; text-align:center;
            }}
            QPushButton#endButton:pressed {{ border-bottom-width:1px; padding-top:11px; }}
        """

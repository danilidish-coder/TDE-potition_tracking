"""Qt emblem, vector watermark, combo arrows and network icon renderers."""
from __future__ import annotations
import base64
from PySide6.QtCore import Qt, QByteArray, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPalette, QIcon, QColor, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget, QComboBox
from position_tracking_artwork import POLICE_EMBLEM_PNG_B64, GREECE_MAP_SVG_B64


def _police_emblem_pixmap(size: int = 82) -> QPixmap:
    """Render the exact approved Hellenic Police emblem shared by TDE-Control-Center."""
    pixmap = QPixmap()
    try:
        pixmap.loadFromData(base64.b64decode(POLICE_EMBLEM_PNG_B64), "PNG")
    except Exception:
        return QPixmap()
    if pixmap.isNull():
        return QPixmap()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class GreeceMapWidget(QWidget):
    """Render the exact approved shared Greece map without redrawing or recolouring it."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(86, 86)
        self.setToolTip("ΕΛΛΑΔΑ")
        try:
            svg_bytes = base64.b64decode(GREECE_MAP_SVG_B64)
            self._renderer = QSvgRenderer(QByteArray(svg_bytes), self)
        except Exception:
            self._renderer = QSvgRenderer(self)

    def set_dark(self, dark: bool):
        # Compatibility with the existing theme code. The approved SVG stays unchanged.
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._renderer.isValid():
            bounds = QRectF(self.rect().adjusted(4, 4, -4, -4))
            natural = self._renderer.defaultSize()
            if natural.isValid() and natural.width() > 0 and natural.height() > 0:
                source_ratio = natural.width() / natural.height()
                target_ratio = bounds.width() / bounds.height() if bounds.height() else source_ratio
                if target_ratio > source_ratio:
                    width = bounds.height() * source_ratio
                    bounds.setX(bounds.x() + (bounds.width() - width) / 2.0)
                    bounds.setWidth(width)
                else:
                    height = bounds.width() / source_ratio
                    bounds.setY(bounds.y() + (bounds.height() - height) / 2.0)
                    bounds.setHeight(height)
            self._renderer.render(painter, bounds)
        painter.end()


class ArrowComboBox(QComboBox):
    """QComboBox with a permanently visible dropdown arrow."""
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(self.palette().color(QPalette.Text))
        arrow_rect = self.rect().adjusted(self.width() - 28, 0, -2, 0)
        painter.drawText(arrow_rect, Qt.AlignCenter, "▼")
        painter.end()


def _network_icon() -> QIcon:
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#0a4f8c"))
    painter.drawRoundedRect(18, 18, 220, 220, 48, 48)
    nodes = [(128, 128, 28), (66, 72, 22), (190, 72, 22), (66, 184, 22), (190, 184, 22)]
    painter.setPen(QPen(QColor("#8fd0ff"), 12, Qt.SolidLine, Qt.RoundCap))
    for x, y, _ in nodes[1:]:
        painter.drawLine(128, 128, x, y)
    for x, y, radius in nodes:
        painter.setPen(QPen(QColor("#dff3ff"), 5))
        painter.setBrush(QColor("#1976c9") if (x, y) != (128, 128) else QColor("#f5f9ff"))
        painter.drawEllipse(x - radius, y - radius, radius * 2, radius * 2)
    painter.end()
    return QIcon(pixmap)


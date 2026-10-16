"""Live booth map, asynchronous refresh and guarded active-position controls."""
from __future__ import annotations
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget, QInputDialog, QDialog
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord
from position_tracking_store import SharedEventStore


class BoothMapWidget(QWidget):
    BOOTH_POS = {
        "7": (0.46, 0.10), "6": (0.52, 0.10),
        "5": (0.52, 0.24), "4": (0.52, 0.32),
        "3": (0.40, 0.40), "2": (0.46, 0.40), "1": (0.52, 0.40),
        "10": (0.40, 0.64), "9": (0.46, 0.64), "8": (0.52, 0.64),
        "11": (0.52, 0.72), "12": (0.52, 0.80),
        "14": (0.46, 0.90), "13": (0.52, 0.90),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active: dict[str, list[dict]] = {}
        self._worker_text_width = 84
        self.setMinimumSize(760, 560)

    @staticmethod
    def _worker_display_name(item: dict) -> str:
        surname = _clean(item.get("surname"))
        given_name = _clean(item.get("given_name"))
        full_name = _clean(item.get("full_name"))
        return _clean(f"{surname} {given_name}") or full_name or "—"

    def set_active(self, items: list[dict]):
        grouped: dict[str, list[dict]] = {}
        for item in items:
            grouped.setdefault(_clean(item.get("position")), []).append(item)
        self.active = grouped
        font = QFont("Segoe UI", 8, QFont.Bold)
        metrics = QFontMetrics(font)
        self._worker_text_width = max(
            [84] + [metrics.horizontalAdvance(self._worker_display_name(item)) for item in items]
        )
        self.update()

    def recommended_dialog_width(self) -> int:
        # The closest booths are 6% of the map width apart. Size the map so
        # the longest worker name fits without requiring manual stretching.
        booth_target = min(max(self._worker_text_width + 20, 92), 190)
        return max(1100, int(booth_target / 0.06) + 90)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        painter.fillRect(self.rect(), QColor("#06101c"))

        # ground / lanes
        painter.setPen(QPen(QColor("#17364e"), 1))
        step = 42
        for x in range(0, w, step): painter.drawLine(x, 0, x, h)
        for y in range(0, h, step): painter.drawLine(0, y, w, y)
        painter.setPen(QPen(QColor("#69849a"), 2, Qt.DashLine))
        for frac in (0.18, 0.34, 0.68, 0.84):
            y = int(h * frac); painter.drawLine(30, y, w - 30, y)

        # buildings
        painter.setPen(QPen(QColor("#38bdf8"), 2))
        painter.setBrush(QColor("#162638"))
        buildings = [(0.10,0.49,0.22,0.10,"ΤΕΛΩΝΕΙΟ"),(0.34,0.49,0.22,0.10,"ΑΣΤΥΝΟΜΙΑ"),(0.58,0.49,0.15,0.10,"ΑΞ/ΚΟΣ ΥΠΗΡΕΣΙΑΣ")]
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        for x,y,bw,bh,label in buildings:
            r=QRectF(w*x,h*y,w*bw,h*bh); painter.drawRoundedRect(r,8,8); painter.drawText(r,Qt.AlignCenter,label)

        # labels
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.setPen(QColor("#4ade80")); painter.drawText(QRectF(w*0.76,h*0.18,w*0.20,h*0.08),Qt.AlignCenter,"ΕΙΣΟΔΟΣ ↑")
        painter.setPen(QColor("#f87171")); painter.drawText(QRectF(w*0.76,h*0.70,w*0.20,h*0.08),Qt.AlignCenter,"ΕΞΟΔΟΣ ↓")

        # booths
        desired_name_width = min(max(self._worker_text_width + 20, 92), 190)
        bw = max(54, min(int(w*0.075), desired_name_width))
        bh = max(52, int(h*0.075))
        for pos,(xf,yf) in self.BOOTH_POS.items():
            x=int(w*xf); y=int(h*yf)
            r=QRectF(x,y,bw,bh)
            people=self.active.get(pos,[])
            occupied=bool(people)
            # subtle pseudo-3D depth: shadow + lower/right faces, then main face
            shadow_r = QRectF(r.x()+7, r.y()+8, r.width(), r.height())
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(0, 0, 0, 95))
            painter.drawRoundedRect(shadow_r, 9, 9)
            painter.setBrush(QColor("#0f5f3f" if occupied else "#064865"))
            painter.drawRoundedRect(QRectF(r.x()+4, r.y()+5, r.width(), r.height()), 9, 9)
            painter.setPen(QPen(QColor("#a7f3d0" if occupied else "#bae6fd"),2))
            painter.setBrush(QColor("#1f9d68" if occupied else "#0878a8"))
            painter.drawRoundedRect(r,9,9)
            # highlight on upper edge for a raised/card-like effect
            painter.setPen(QPen(QColor(255,255,255,70),1))
            painter.drawLine(int(r.x()+7), int(r.y()+4), int(r.right()-7), int(r.y()+4))
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 11, QFont.Bold))
            painter.drawText(QRectF(r.x(),r.y()+2,r.width(),18),Qt.AlignCenter,f"ΘΕΣΗ {pos}")
            if people:
                names=[]
                for item in people[:2]:
                    worker_name = self._worker_display_name(item)
                    ts=_clean(item.get("timestamp")).replace("T"," ")
                    hhmm=ts[11:16] if len(ts)>=16 else ""
                    direction=_clean(item.get("direction"))
                    names.append(f"{worker_name}\n{direction} {hhmm}".strip())
                if len(people)>2: names.append(f"+{len(people)-2} ακόμη")
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.drawText(QRectF(r.x()+3,r.y()+19,r.width()-6,r.height()-21),Qt.AlignCenter|Qt.TextWordWrap,"\n".join(names))


class LiveMapDialog(QDialog):

    def __init__(self, store: SharedEventStore, people_by_agms: dict[str, PersonnelRecord], officer_getter, parent=None):
        super().__init__(parent)
        self.store = store
        self.people_by_agms = people_by_agms
        self.officer_getter = officer_getter
        self._live_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='TDE-live-map')
        self._live_future = None
        self.setWindowTitle('ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ - Ζωντανή εικόνα θέσεων')
        self.resize(1100, 820)
        self.setStyleSheet('\n                QDialog{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #eef5f9,stop:1 #dfeaf1);}\n                QLabel{color:#193b50;}\n            ')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel('ΖΩΝΤΑΝΗ ΕΙΚΟΝΑ ΘΕΣΕΩΝ')
        title.setStyleSheet('font-size:22px;font-weight:900;color:#123f5a;letter-spacing:1px')
        self.updated = QLabel('')
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.updated)
        lay.addLayout(top)
        self.map = BoothMapWidget()
        lay.addWidget(self.map, 1)
        self.other = QLabel('')
        self.other.setWordWrap(True)
        self.other.setStyleSheet('background:#ffffff;border:1px solid #cfdae2;padding:10px 12px;border-radius:12px;color:#36596f;font-weight:600')
        lay.addWidget(self.other)
        action_row = QHBoxLayout()
        self.active_person = QComboBox()
        self.active_person.setMinimumHeight(40)
        self.active_person.setMinimumWidth(350)
        self.end_active_btn = QPushButton('ΛΗΞΗ ΕΝΕΡΓΗΣ ΘΕΣΗΣ')
        self.end_active_btn.setMinimumHeight(40)
        self.end_active_btn.setStyleSheet('font-weight:900')
        self.end_active_btn.clicked.connect(self._end_selected_active)
        self.edit_start_btn = QPushButton('ΔΙΟΡΘΩΣΗ ΩΡΑΣ ΕΝΑΡΞΗΣ')
        self.edit_start_btn.setMinimumHeight(40)
        self.edit_start_btn.clicked.connect(self._correct_selected_start)
        action_row.addWidget(QLabel('Ενεργός αστυνομικός:'))
        action_row.addWidget(self.active_person, 1)
        action_row.addWidget(self.end_active_btn)
        action_row.addWidget(self.edit_start_btn)
        lay.addLayout(action_row)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)
        self.refresh()

    def _selected_active(self) -> dict | None:
        agms = _clean(self.active_person.currentData())
        if not agms:
            return None
        return self.store.get_active(agms)

    def _correct_selected_start(self):
        officer = self.officer_getter() if callable(self.officer_getter) else None
        if not officer:
            QMessageBox.warning(self, 'ΑΞΥΠ', 'Εισαγάγετε έγκυρο Α.Γ.Μ.Σ. ΑΞΥΠ.')
            return
        active = self._selected_active()
        if not active:
            QMessageBox.warning(self, 'Διόρθωση', 'Επιλέξτε ενεργό αστυνομικό.')
            return
        started = datetime.fromisoformat(active['timestamp'])
        proposed, ok = QInputDialog.getText(self, 'ΔΙΟΡΘΩΣΗ ΩΡΑΣ ΕΝΑΡΞΗΣ', 'Πραγματική ώρα έναρξης (ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ):', QLineEdit.Normal, started.strftime('%d/%m/%Y %H:%M'))
        if not ok:
            return
        try:
            revised = datetime.strptime(_clean(proposed), '%d/%m/%Y %H:%M')
        except ValueError:
            QMessageBox.warning(self, 'Διόρθωση', 'Χρησιμοποιήστε ΗΗ/ΜΜ/ΕΕΕΕ ΩΩ:ΛΛ.')
            return
        reason, ok = QInputDialog.getText(self, 'Αιτιολογία διόρθωσης', 'Αιτιολογία (π.χ. προσωρινή διακοπή εφαρμογής):')
        if not ok:
            return
        if QMessageBox.question(self, 'Επιβεβαίωση', f"ΑΓΜΣ: {active.get('agms')}\nΠροηγούμενη: {started:%d/%m/%Y %H:%M}\nΝέα: {revised:%d/%m/%Y %H:%M}\nΑιτία: {_clean(reason)}\n\nΝα αποθηκευτεί η διόρθωση;", QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.store.correct_active_start(_clean(active.get('agms')), revised, officer, reason)
            self.refresh()
            QMessageBox.information(self, 'Διόρθωση', 'Η νέα ώρα καταγράφηκε με ιστορικό αλλαγής.')
        except Exception as exc:
            QMessageBox.critical(self, 'Διόρθωση', str(exc))

    def _end_selected_active(self):
        officer = self.officer_getter() if callable(self.officer_getter) else None
        if not officer:
            QMessageBox.warning(self, 'Αξιωματικός Υπηρεσίας', 'Πληκτρολογήστε πρώτα έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας στο κύριο παράθυρο.')
            return
        active = self._selected_active()
        if not active:
            QMessageBox.information(self, 'Λήξη ενεργής θέσης', 'Η επιλεγμένη καταγραφή δεν είναι πλέον ενεργή.')
            self.refresh()
            return
        agms = _clean(active.get('agms'))
        person = self.people_by_agms.get(agms)
        if not person:
            person = PersonnelRecord(agms=agms, rank=_clean(active.get('rank')), surname=_clean(active.get('surname')), given_name=_clean(active.get('given_name')))
        name = _clean(f'{person.rank} {person.surname} {person.given_name}') or f'ΑΓΜΣ {agms}'
        pos = _clean(active.get('position'))
        direction = _clean(active.get('direction'))
        started = _clean(active.get('timestamp')).replace('T', ' ')
        confirm = QMessageBox.question(self, 'Επιβεβαίωση λήξης ενεργής θέσης', f'{name}\nΘέση {pos} — {direction}\nΈναρξη: {started}\n\nΝα καταχωριστεί ΛΗΞΗ από τον Αξιωματικό Υπηρεσίας;', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return
        try:
            event = self.store.end(person)
            self.store.log_admin_action('ACTIVE_POSITION_ENDED_BY_OFFICER', {'officer_agms': officer.agms, 'officer_name': officer.full_name, 'target_agms': agms, 'target_name': person.full_name, 'position': pos, 'direction': direction, 'start_at': _clean(active.get('timestamp')), 'end_at': _clean(event.get('timestamp'))})
            QMessageBox.information(self, 'Λήξη ενεργής θέσης', f"Η θέση του {name} έκλεισε στις {_clean(event.get('timestamp')).replace('T', ' ')}.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, 'Δεν καταχωρίστηκε', str(exc))

    def closeEvent(self, event):
        self.timer.stop()
        self._live_pool.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)

    def refresh(self):
        future = self._live_future
        if future is None:
            self._live_future = self._live_pool.submit(self.store.active_all)
            return
        if not future.done():
            return
        self._live_future = None
        try:
            items = future.result()
        except Exception:
            self.updated.setText('ΑΠΩΛΕΙΑ ΣΥΝΔΕΣΗΣ — αναμονή επαναφοράς')
            return
        self.map.set_active(items)
        current_agms = _clean(self.active_person.currentData())
        self.active_person.blockSignals(True)
        self.active_person.clear()
        for item in items:
            agms = _clean(item.get('agms'))
            label = _clean(f"{item.get('rank', '')} {item.get('surname', '')} {item.get('given_name', '')}") or _clean(item.get('full_name')) or f'ΑΓΜΣ {agms}'
            pos = _clean(item.get('position'))
            direction = _clean(item.get('direction'))
            self.active_person.addItem(f'{label} — Θέση {pos} {direction}', agms)
        if current_agms:
            idx = self.active_person.findData(current_agms)
            if idx >= 0:
                self.active_person.setCurrentIndex(idx)
        self.active_person.blockSignals(False)
        self.end_active_btn.setEnabled(bool(items))
        self.edit_start_btn.setEnabled(bool(items))
        recommended = self.map.recommended_dialog_width()
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            target_width = min(recommended, max(1100, available.width() - 60))
            target_height = min(820, max(700, available.height() - 80))
        else:
            target_width = min(recommended, 1600)
            target_height = 820
        if self.width() < target_width:
            self.resize(target_width, target_height)
        other = []
        for x in items:
            pos = _clean(x.get('position'))
            if pos not in BoothMapWidget.BOOTH_POS:
                other.append(f"{x.get('rank', '')} {x.get('full_name', '')} — {pos} — {x.get('direction', '')} — από {_clean(x.get('timestamp')).replace('T', ' ')}")
        self.other.setText('Άλλες ενεργές θέσεις: ' + (' | '.join(other) if other else 'καμία'))
        self.updated.setText('Ενημέρωση: ' + datetime.now().strftime('%H:%M:%S'))


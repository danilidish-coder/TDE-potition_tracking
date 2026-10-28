"""Officer administration, audit/backup actions and live-view navigation."""
from __future__ import annotations
import json
from functools import partial
from shiboken6 import isValid
from datetime import datetime
from position_tracking_common import _clean
from position_tracking_ui_map import LiveMapDialog
from position_tracking_theme import THEME_DARK, THEME_LIGHT, _theme_stylesheet
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QInputDialog, QDialog, QListWidget


def _open_shift_members(store):
    try:
        store.log_admin_action('OFFICER_DUTY_PANEL_OPENED')
    except Exception:
        pass
    return store.sync_active_shift()


class AdministrationMixin:
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
        for button in (start_shift, end_shift, accept_btn, exclude_btn):
            button.setEnabled(False)
        row2.addWidget(start_shift); row2.addWidget(end_shift); row2.addWidget(live); lay.addLayout(row2)

        def selected_officer():
            return self._people_by_agms.get(_clean(officer_agms.text()))

        def officer_changed(*_):
            p = selected_officer()
            officer_name.setText(_clean(f"{p.rank} {p.full_name}") if p else "—")

        membership = {'shift_id': ''}

        def refresh_members():
            if self.store and isValid(dlg):
                self._run_shift_job(self.store.sync_active_shift, render_members)

        def render_members(shift):
            if not isValid(dlg):
                return
            membership['shift_id'] = shift['shift_id'] if shift else ''
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
            self._run_shift_job(partial(self.store.set_shift_member_state,
                item.data(Qt.UserRole), state, membership['shift_id']), lambda result: refresh_members())

        def do_start():
            p = selected_officer()
            if not p:
                QMessageBox.warning(dlg, "Έλεγχος", "Πληκτρολογήστε έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας."); return
            def started(shift):
                if not isValid(dlg):
                    return
                QMessageBox.information(dlg, "Βάρδια", f"Έναρξη βάρδιας {shift['start_at'].replace('T',' ')}.\nΕλέγξτε τους ΑΠΟΔΕΚΤΟΥΣ και εξαιρέστε όποιον ανήκει στην προηγούμενη βάρδια.")
                refresh_members()
            self._run_shift_job(partial(self.store.start_officer_shift, p), started)

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
        self._run_shift_job(partial(_open_shift_members, self.store), render_members)
        try:
            dlg.exec()
        finally:
            timer.stop()
            dlg.deleteLater()


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


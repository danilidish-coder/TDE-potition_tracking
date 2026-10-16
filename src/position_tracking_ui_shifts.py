"""Officer shift preview, membership approval and asynchronous shift status."""
from __future__ import annotations
import json
from datetime import datetime
from position_tracking_common import _clean
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QDialog, QListWidget, QListWidgetItem


class ShiftControllerMixin:
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


    def _shift_admin(self):
        self._admin()


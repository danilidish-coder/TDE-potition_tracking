"""Shift completion modal with guarded single and bulk END actions."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget, QDialog, QListWidget, QListWidgetItem


class ShiftEndDialogMixin:
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


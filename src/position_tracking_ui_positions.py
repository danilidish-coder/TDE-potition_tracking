"""Durable local position actions, offline reconciliation and visible conflict handling."""
from __future__ import annotations
import os
import socket
import time
from pathlib import Path
from position_tracking_machine_queue import _local_root
from position_tracking_handoff import reconcile_handoff_before_replay
from position_tracking_bootstrap import cache_windows_client
from position_tracking_common import _clean
from position_tracking_store import SharedEventStore
from position_tracking_personnel import PersonnelRecord
from position_tracking_store_io import BusyError
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QInputDialog, QDialog, QListWidget


class PositionActionsMixin:
    def _offline_conflicts_dialog(self):
        officer = self._officer_selected()
        if not officer:
            QMessageBox.warning(self, "ΑΞΥΠ", "Συμπληρώστε πρώτα έγκυρο ΑΓΜΣ ΑΞΥΠ.")
            return
        conflicts = self.offline.conflicts()
        if not conflicts:
            QMessageBox.information(self, "Offline", "Δεν υπάρχουν εκκρεμείς ασυμφωνίες.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("ΑΞΥΠ — ΑΣΥΜΦΩΝΙΕΣ ΣΥΓΧΡΟΝΙΣΜΟΥ")
        dlg.resize(820, 520)
        lay = QVBoxLayout(dlg)
        label = QLabel("Η παρακάτω τοπική εγγραφή ΔΕΝ καταχωρίστηκε κεντρικά. "
                       "Ελέγξτε την πραγματική εργασία πριν απορρίψετε την εγγραφή.")
        label.setWordWrap(True)
        lay.addWidget(label)
        listing = QListWidget()
        for rec in conflicts:
            listing.addItem(f"{rec['created_at']} | ΑΓΜΣ {rec['agms']} | "
                            f"{rec['kind']} | ΘΕΣΗ {rec['position']} | {rec['error']}")
            listing.item(listing.count()-1).setData(Qt.UserRole, rec['id'])
        lay.addWidget(listing, 1)
        row = QHBoxLayout()
        reject = QPushButton("ΑΠΟΡΡΙΨΗ ΜΕ ΑΙΤΙΟΛΟΓΙΑ")
        close = QPushButton("ΚΛΕΙΣΙΜΟ")
        row.addWidget(reject); row.addWidget(close); lay.addLayout(row)
        def resolve():
            item = listing.currentItem()
            if not item:
                return
            reason, ok = QInputDialog.getText(dlg, "Αιτιολογία", "Γιατί απορρίπτεται η τοπική εγγραφή;")
            if not ok: return
            if QMessageBox.question(dlg, "ΕΠΙΒΕΒΑΙΩΣΗ",
                "Η καταχώριση δεν θα μεταφερθεί κεντρικά. Διατηρείται στο ιστορικό. Συνέχεια;",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                self.offline.resolve_conflict(_clean(item.data(Qt.UserRole)), officer.agms, reason)
                dlg.accept()
                self._refresh_info()
                self._agms_changed()
            except Exception as exc:
                QMessageBox.critical(dlg, "Ασυμφωνία", str(exc))
        reject.clicked.connect(resolve)
        close.clicked.connect(dlg.reject)
        dlg.exec()


    def _offline_tick(self):
        if getattr(self, "_exit_in_progress", False):
            return
        if self._offline_future is not None:
            if not self._offline_future.done():
                return
            future = self._offline_future
            self._offline_future = None
            try:
                connected, result = future.result()
                self.store = connected
                self._handoff_initial_error = ""
                if result.get("conflicts"):
                    self.info.setText("ΑΣΥΜΦΩΝΙΑ ΑΠΟΣΥΝΔΕΔΕΜΕΝΩΝ ΚΑΤΑΧΩΡΙΣΕΩΝ — έλεγχος ΑΞΥΠ")
                self._refresh_info()
            except Exception as exc:
                self.store = None
                self._refresh_info()
                self.info.setText(
                    "ΔΕΝ ΟΛΟΚΛΗΡΩΘΗΚΕ Ο ΣΥΓΧΡΟΝΙΣΜΟΣ / HANDOFF: "
                    + str(exc)[:220]
                    + " — οι εκκρεμείς εγγραφές παραμένουν αποθηκευμένες."
                )
            self._agms_changed()
        if self._offline_future is not None:
            return
        if not self.config.central_root:
            return
        def work():
            if not Path(self.config.central_root).is_dir():
                raise BusyError("Ο κεντρικός φάκελος δεν είναι διαθέσιμος.")
            store = SharedEventStore(self.config.central_root)
            report = reconcile_handoff_before_replay(
                store, self.offline, PersonnelRecord, socket.gethostname(),
                os.environ.get("USERNAME") or os.environ.get("USER") or "",
            )
            if self.config.shared_exe_path and time.monotonic() - self._last_bootstrap_check > 300:
                self._last_bootstrap_check = time.monotonic()
                try:
                    cache_windows_client(self._services.local_root(), self.config.shared_exe_path)
                except Exception:
                    pass  # cache update must not block shifts
            return store, report
        self._offline_future = self._network_pool.submit(work)


    def _position_action(self, kind: str, person: PersonnelRecord, position: str = "", direction: str = ""):
        if getattr(self, "_exit_in_progress", False):
            return
        if self._handoff_initial_error:
            QMessageBox.warning(
                self, "ΑΝΑΜΟΝΗ ΣΥΜΦΩΝΙΑΣ WINDOWS",
                "Δεν επιβεβαιώθηκε η λήξη του προηγούμενου χρήστη. "
                + self._handoff_initial_error,
            )
            return
        if self._position_operation_future is not None:
            QMessageBox.warning(self, "Καταχώριση", "Υπάρχει ήδη εντολή σε εξέλιξη.")
            return
        self.start_btn.setEnabled(False)
        self.end_btn.setEnabled(False)
        self.active_status.setText("ΤΟΠΙΚΗ ΑΠΟΘΗΚΕΥΣΗ ΚΑΤΑΧΩΡΙΣΗΣ…")
        def work():
            # Never wait on a sleeping/disconnected SMB host while a booth
            # action is being recorded. Store the operation locally first;
            # a separate network worker performs idempotent central replay.
            result = self.offline.enqueue(kind, person, position, direction, self.client_id)
            result["pending_sync"] = True
            result["conflict"] = bool(self.offline.conflicts())
            return result
        # Even a failed/ambiguous enqueue prevents the never-used-session exit
        # shortcut. Confirmation of a real position must retain its strict path.
        self._position_activity_attempted = True
        future = self._position_pool.submit(work)
        self._position_operation_future = future
        def poll():
            if not future.done():
                QTimer.singleShot(200, poll)
                return
            self._position_operation_future = None
            try:
                outcome = future.result()
            except Exception as exc:
                QMessageBox.critical(self, "Δεν καταχωρίστηκε", str(exc))
            else:
                if outcome.get("conflict"):
                    QMessageBox.warning(self, "ΑΣΥΜΦΩΝΙΑ", "Απαιτείται έλεγχος ΑΞΥΠ. Η τοπική εγγραφή δεν διαγράφηκε.")
                elif outcome["pending_sync"]:
                    QMessageBox.warning(self, "ΕΚΚΡΕΜΕΙ ΣΥΓΧΡΟΝΙΣΜΟΣ", "Η καταχώριση φυλάχθηκε ΤΟΠΙΚΑ. Δεν έχει ακόμη επιβεβαιωθεί κεντρικά.")
                else:
                    QMessageBox.information(self, "Καταχώριση", f"{kind}: Η καταχώριση επιβεβαιώθηκε κεντρικά.")
            self._refresh_info()
            self._agms_changed()
            # Launch central reconciliation asynchronously; the button
            # remains responsive regardless of central SMB availability.
            self._offline_tick()
        QTimer.singleShot(100, poll)


    def _start(self):
        person = self._selected()
        if not person:
            QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού.")
            return
        position = _clean(self.position.currentText())
        direction = _clean(self.direction.currentText()).upper()
        if position not in {str(i) for i in range(1, 15)}:
            QMessageBox.warning(self, "Θέση", "Επιλέξτε θέση 1 έως 14.")
            return
        self._position_action("START", person, position, direction)


    def _end(self):
        person = self._selected()
        if not person:
            QMessageBox.warning(self, "Έλεγχος", "Επιλέξτε λίστα προσωπικού.")
            return
        self._position_action("END", person)


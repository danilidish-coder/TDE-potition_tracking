"""Safe window close, explicit operator exit and asynchronous client cleanup."""
from __future__ import annotations
import time
from position_tracking_common import _clean
from position_tracking_store_io import BusyError
from PySide6.QtCore import QTimer
from position_tracking_personnel import PersonnelRecord
from PySide6.QtWidgets import QApplication, QMessageBox


class WindowLifecycleMixin:
    def closeEvent(self, event):
        if self._force_exit:
            event.accept()
            return
        event.ignore()
        self.showMinimized()


    def _cleanup_client(self):
        # aboutToQuit must never perform SMB I/O. Normal confirmed exit removes
        # its heartbeat in the worker; abrupt shutdown lets the heartbeat expire.
        if getattr(self, "_client_cleanup_started", False):
            return
        self._client_cleanup_started = True
        self._agms_query_serial = getattr(self, "_agms_query_serial", 0) + 1
        for name in ("shift_timer", "communication_timer", "offline_timer"):
            timer = getattr(self, name, None)
            if timer is not None:
                timer.stop()
        for name in ("_network_pool", "_position_pool", "_state_pool"):
            pool = getattr(self, name, None)
            if pool is not None:
                pool.shutdown(wait=False, cancel_futures=True)


    def _end_own_active_positions(self, store=None) -> int:
        """Close only START records created by this exact app process."""
        store = store or self.store
        if not store:
            raise BusyError("Δεν επιβεβαιώθηκε σύνδεση με τα κεντρικά δεδομένα.")
        mine = [
            item for item in store.active_all()
            if _clean(item.get("client_id")) == self.client_id
        ]
        for item in mine:
            member = PersonnelRecord(
                agms=_clean(item.get("agms")),
                rank=_clean(item.get("rank")),
                surname=_clean(item.get("surname")),
                given_name=_clean(item.get("given_name")),
            )
            store.end(member, expected_start_event_id=_clean(item.get("event_id")))
        return len(mine)


    def _request_real_exit(self):
        answer = QMessageBox.question(
            self,
            "Έξοδος από το πρόγραμμα",
            "Να κλείσει η εφαρμογή;\n\n"
            "Απλό κλείσιμο χωρίς ΛΗΞΗ επιτρέπεται μόνο όταν αποδεικνύεται "
            "ότι αυτό το παράθυρο δεν άνοιξε θέση και δεν υπάρχουν ενεργές "
            "ή εκκρεμείς τοπικές καταγραφές.\n\n"
            "Διαφορετικά, οι θέσεις αυτού του παραθύρου απαιτούν "
            "επιβεβαιωμένη ΛΗΞΗ πριν από την έξοδο. "
            "Το κλείσιμο εφαρμογής δεν αποτελεί αποδέσμευση άλλων θέσεων.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._start_confirmed_exit()

    def _start_confirmed_exit(self, command_id: str = ""):
        if getattr(self, "_exit_in_progress", False):
            return
        self._exit_in_progress = True
        self.start_btn.setEnabled(False)
        self.end_btn.setEnabled(False)
        self.info.setText("ΕΛΕΓΧΟΣ ΑΣΦΑΛΟΥΣ ΕΞΟΔΟΥ — η εφαρμογή παραμένει ανοικτή.")
        offline_future = self._offline_future
        local_future = self._position_operation_future
        map_future = getattr(self, "_map_mutation_future", None)
        store = self.store

        def work():
            connected = store
            # Local actions use this same single-worker executor, so any prior
            # enqueue is durable before this closure starts. Reconciliation has
            # a separate worker; wait without blocking Qt or overtaking its END.
            if local_future is not None:
                local_future.result(timeout=0)
            if map_future is not None and not map_future.done():
                map_future.result(timeout=31)
            def can_close_locally():
                background_settled = all(
                    future is None or future.done() for future in (
                        offline_future, getattr(self, "_communication_future", None),
                        getattr(self, "_shift_future", None), getattr(self, "_shift_closure_future", None),
                        getattr(self, "_agms_future", None), getattr(self, "_shift_status_future", None),
                    )
                )
                return (not command_id and getattr(self, "_position_activity_attempted", None) is False
                        and not getattr(self, "_handoff_initial_error", "") and background_settled
                        and self.offline.proves_no_position_obligations())
            if can_close_locally():
                # Application closure only: no END, ACK or absent-share access.
                return "local_idle"
            if offline_future is not None:
                try:
                    connected, _ = offline_future.result(timeout=31)
                except Exception:
                    # An initially pending connection may have just failed. Once
                    # settled, re-prove idle state; a timeout on running work or
                    # any journal obligation still fails closed.
                    if can_close_locally():
                        return "local_idle"
                    raise
            if self.offline.pending_count():
                raise BusyError("Υπάρχουν εκκρεμείς τοπικές καταχωρίσεις. Περιμένετε τον συγχρονισμό πριν από την έξοδο.")
            self._end_own_active_positions(connected)
            if command_id:
                connected.acknowledge_command(command_id, self.client_id)
            try:
                connected.remove_client_heartbeat(self.client_id)
            except Exception:
                pass  # heartbeat expiry does not change confirmed END receipts
            return "centrally_confirmed"

        future = self._position_pool.submit(work)
        self._exit_future = future
        started = time.monotonic()

        def poll():
            if not future.done():
                if time.monotonic() - started > 10:
                    self.info.setText("ΑΝΑΜΟΝΗ ΚΕΝΤΡΙΚΟΥ ΓΙΑ ΑΣΦΑΛΗ ΕΞΟΔΟ — δεν επιβεβαιώθηκε τερματισμός. Μην επαναλάβετε την εντολή.")
                QTimer.singleShot(100, poll)
                return
            try:
                self._exit_mode = future.result()
            except Exception as exc:
                self._exit_in_progress = False
                self.info.setText("Η ΕΞΟΔΟΣ ΔΕΝ ΕΠΙΒΕΒΑΙΩΘΗΚΕ — η εφαρμογή παραμένει ανοικτή.")
                self._agms_changed()
                QMessageBox.critical(
                    self, "Η έξοδος δεν ολοκληρώθηκε",
                    f"Δεν αποδείχθηκε ασφαλές κλείσιμο ή επιβεβαιωμένη ΛΗΞΗ.\n{exc}\n"
                    "Οι καταγραφές διατηρούνται. Ελέγξτε τον κεντρικό υπολογιστή ή ενημερώστε τον ΑΞΥΠ.",
                )
                return
            self._force_exit = True
            self._cleanup_client()
            QApplication.quit()

        QTimer.singleShot(100, poll)

"""Safe window close, explicit operator exit and asynchronous client cleanup."""
from __future__ import annotations
from position_tracking_common import _clean
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
        try:
            self._network_pool.shutdown(wait=False, cancel_futures=True)
            self._position_pool.shutdown(wait=False, cancel_futures=True)
            self._state_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        if self.store:
            try:
                self.store.remove_client_heartbeat(self.client_id)
            except Exception:
                pass


    def _end_own_active_positions(self) -> int:
        """Close only START records created by this exact app process."""
        if not self.store:
            return 0
        mine = [
            item for item in self.store.active_all()
            if _clean(item.get("client_id")) == self.client_id
        ]
        for item in mine:
            member = PersonnelRecord(
                agms=_clean(item.get("agms")),
                rank=_clean(item.get("rank")),
                surname=_clean(item.get("surname")),
                given_name=_clean(item.get("given_name")),
            )
            self.store.end(member, expected_start_event_id=_clean(item.get("event_id")))
        return len(mine)


    def _request_real_exit(self):
        answer = QMessageBox.question(
            self,
            "Έξοδος από το πρόγραμμα",
            "Να κλείσει πραγματικά η εφαρμογή?\\n\\n"
            "Οι ενεργές θέσεις που ανοίχθηκαν από αυτό το παράθυρο "
            "θα λάβουν ΛΗΞΗ πριν κλείσει το πρόγραμμα.\\n"
            "Αν δεν είναι διαθέσιμος ο κεντρικός φάκελος, η έξοδος "
            "δεν θα ολοκληρωθεί με ψευδή επιβεβαίωση.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self._end_own_active_positions()
        except Exception as exc:
            QMessageBox.critical(
                self, "Η λήξη δεν καταχωρίστηκε",
                f"Δεν επιβεβαιώθηκε η αποδέσμευση της θέσης.\\n{exc}\\n"
                "Ελέγξτε τον κεντρικό υπολογιστή ή ζητήστε από τον ΑΞΥΠ "
                "να ολοκληρώσει τη θέση από τη ζωντανή εικόνα."
            )
            return
        self._force_exit = True
        self._cleanup_client()
        QApplication.quit()


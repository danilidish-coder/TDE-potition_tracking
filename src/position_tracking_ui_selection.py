"""Personnel selection and asynchronous active-position button state."""
from __future__ import annotations
import time
from position_tracking_common import _clean
from position_tracking_personnel import PersonnelRecord
from PySide6.QtCore import QTimer


class PersonnelSelectionMixin:
    def _selected(self) -> PersonnelRecord | None:
        return self._people_by_agms.get(_clean(self.agms_input.text()))


    def _officer_selected(self) -> PersonnelRecord | None:
        return self._people_by_agms.get(_clean(self.officer_agms.text()))


    def _officer_changed(self, *_):
        p = self._officer_selected()
        self.officer_name.setText(_clean(f"{p.rank} {p.surname} {p.given_name}") if p else "—")
        self._refresh_shift_status()


    def _agms_changed(self, *_):
        self._agms_query_serial = getattr(self, "_agms_query_serial", 0) + 1
        serial = self._agms_query_serial
        person = self._selected()
        self.start_btn.setEnabled(False)
        self.end_btn.setEnabled(False)
        if not person:
            self.person_name.setText("—")
            self.active_status.setText(
                "Ο Α.Γ.Μ.Σ. δεν βρέθηκε στο προσωπικό"
                if _clean(self.agms_input.text()) else "Πληκτρολογήστε Α.Γ.Μ.Σ."
            )
            return
        self.person_name.setText(_clean(f"{person.rank} {person.surname} {person.given_name}"))
        if self._position_operation_future is not None:
            self.active_status.setText("ΚΑΤΑΧΩΡΙΣΗ ΣΕ ΕΞΕΛΙΞΗ — μην την επαναλάβετε.")
            return
        local = self.offline.local_active(person.agms)
        if self.offline.conflicts():
            self.active_status.setText("ΑΣΥΜΦΩΝΙΑ ΣΥΓΧΡΟΝΙΣΜΟΥ — ΕΝΗΜΕΡΩΣΤΕ ΤΟΝ ΑΞΥΠ")
            return
        if not self.store or self.offline.pending_count():
            self.active_status.setText(
                (f"ΤΟΠΙΚΗ ΘΕΣΗ {local.get('position','')} — ΕΚΚΡΕΜΕΙ ΚΕΝΤΡΙΚΗ ΕΠΙΒΕΒΑΙΩΣΗ"
                 if local else "ΕΚΤΟΣ ΣΥΝΔΕΣΗΣ — νέα έναρξη θα παραμείνει ΠΡΟΣΩΡΙΝΗ")
            )
            self.end_btn.setEnabled(bool(local))
            self.start_btn.setEnabled(not bool(local))
            return
        self.active_status.setText("ΕΛΕΓΧΟΣ ΕΝΕΡΓΗΣ ΘΕΣΗΣ — αναμονή κεντρικού.")
        def load_remote():
            record = self.store.get_active(person.agms)
            self.offline.remember(person.agms, record)
            return record
        future = self._state_pool.submit(load_remote)
        query_started = time.monotonic()

        def poll():
            if serial != self._agms_query_serial:
                return
            if not future.done():
                if time.monotonic() - query_started > 3.0:
                    local = self.offline.local_active(person.agms)
                    self.active_status.setText("ΔΙΚΤΥΟ ΧΩΡΙΣ ΑΠΟΚΡΙΣΗ — τοπική λειτουργία με εκκρεμή επιβεβαίωση")
                    self.start_btn.setEnabled(not bool(local))
                    self.end_btn.setEnabled(bool(local))
                    return
                QTimer.singleShot(200, poll)
                return
            try:
                active = future.result()
            except Exception:
                local = self.offline.local_active(person.agms)
                self.active_status.setText("ΧΩΡΙΣ ΣΥΝΔΕΣΗ — τοπικές εγγραφές ΕΚΚΡΕΜΟΥΝ")
                self.start_btn.setEnabled(not bool(local))
                self.end_btn.setEnabled(bool(local))
                return
            if self._position_operation_future is not None:
                return
            if active:
                ts = _clean(active.get("timestamp", "")).replace("T", " ")
                self.active_status.setText(
                    f"ΕΝΕΡΓΗ: ΘΕΣΗ {active.get('position','')} — "
                    f"{active.get('direction','')} — από {ts}"
                )
                self.end_btn.setEnabled(True)
            else:
                self.active_status.setText("Δεν υπάρχει ανοικτή καταχώριση")
                self.start_btn.setEnabled(True)

        QTimer.singleShot(100, poll)


    @staticmethod
    def _suggested_direction(position: str) -> str:
        pos = _clean(position)
        if pos.isdigit():
            n = int(pos)
            if 1 <= n <= 7: return "ΕΙΣΟΔΟΣ"
            if 8 <= n <= 14: return "ΕΞΟΔΟΣ"
        return "ΕΙΣΟΔΟΣ"


    def _position_changed(self, position: str):
        suggested = self._suggested_direction(position)
        idx = self.direction.findText(suggested)
        if idx >= 0: self.direction.setCurrentIndex(idx)


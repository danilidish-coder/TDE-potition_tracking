"""Local settings, read-only personnel cache selection and configuration feedback."""
from __future__ import annotations
import os
import shutil
import socket
import sys
from pathlib import Path
from position_tracking_machine_queue import _local_root
from position_tracking_common import _clean
from position_tracking_settings import _app_dir
from position_tracking_personnel import PersonnelRepository
from PySide6.QtWidgets import QMessageBox, QFileDialog


class ConfigurationMixin:
    def _find_personnel_file(self) -> Path | None:
        candidates = []
        # Cached roster first, so a powered-off shared host never blocks
        # the operator window during Windows account login.
        cache = self._services.local_root() / "roster"
        for name in ("ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"):
            candidates.append(cache / name)
        legacy = Path(self.config.personnel_file) if _clean(self.config.personnel_file) else None
        if legacy:
            candidates.append(legacy)
        for base in (self._services.app_dir() / "CONFIG", self._services.app_dir(), Path(self.config.central_root)):
            for name in ("ΠΡΟΣΩΠΙΚΟ.xlsx", "ΠΡΟΣΩΠΙΚΟ.xlsm", "PROSOPIKO.xlsx", "PROSOPIKO.xlsm"):
                candidates.append(base / name)
        for path in candidates:
            if path.is_file():
                return path
        return None


    def _apply_config(self):
        self.position.clear(); self.position.addItems(self.config.positions or [])
        self._position_changed(self.position.currentText())
        if not self.config.central_root:
            self.config.central_root = str(self._services.app_dir() / ".tde_runtime")
        # Never touch a possibly disconnected UNC path on the GUI thread.
        self.store = None
        try:
            self.offline.auto_close_previous_windows_users(
                socket.gethostname(), os.environ.get("USERNAME") or os.environ.get("USER") or "")
        except Exception as exc:
            self._handoff_initial_error = str(exc)
        if getattr(sys, "frozen", False) and not self.config.shared_exe_path:
            self.config.shared_exe_path = str(Path(sys.executable).resolve())
        personnel = self._find_personnel_file()
        if personnel:
            try:
                self._load_people(str(personnel))
                if not self.config.personnel_file:
                    self.config.personnel_file = str(personnel)
            except Exception as exc:
                self.info.setText(f"Πρόβλημα προσωπικού: {exc}")
        self.config.save()
        self._refresh_info(); self._agms_changed(); self._refresh_shift_status()


    def _refresh_info(self):
        if self._handoff_initial_error:
            self.info.setText(
                "ΕΚΚΡΕΜΕΙ Η ΑΛΛΑΓΗ ΧΡΗΣΤΗ WINDOWS — " + self._handoff_initial_error
            )
            return
        if not self.store:
            self.info.setText("ΧΩΡΙΣ ΚΕΝΤΡΙΚΟ — τοπικές εκκρεμείς εγγραφές, θα γίνει συγχρονισμός μόλις επιστρέψει η σύνδεση.")
        elif self.offline.conflicts():
            self.info.setText("ΑΣΥΜΦΩΝΙΑ ΣΥΓΧΡΟΝΙΣΜΟΥ — απαιτείται έλεγχος ΑΞΥΠ.")
        elif self.offline.pending_count():
            self.info.setText(f"ΑΝΑΜΟΝΗ ΣΥΓΧΡΟΝΙΣΜΟΥ: {self.offline.pending_count()} καταχωρίσεις.")
        elif self.store and self.people:
            self.info.setText(f"Σύστημα έτοιμο — Λίστα προσωπικού: {len(self.people)} άτομα")
        else:
            self.info.setText("Δεν έχει επιλεγεί λίστα προσωπικού.")


    def _save_config(self):
        self.config.positions = [self.position.itemText(i) for i in range(self.position.count()) if _clean(self.position.itemText(i))]
        self.config.save(); self._refresh_info()


    def _load_people(self, path: str):
        self.people = PersonnelRepository.load(path)
        self._people_by_agms = {_clean(p.agms): p for p in self.people}
        try:
            cached = self._services.local_root() / "roster" / Path(path).name
            cached.parent.mkdir(parents=True, exist_ok=True)
            if Path(path).resolve() != cached.resolve():
                shutil.copy2(path, cached)
        except OSError:
            pass
        self._agms_changed(); self._officer_changed()


    def _choose_personnel_list(self):
        start_dir = str(Path(self.config.personnel_file).parent) if _clean(self.config.personnel_file) else str(self._services.app_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Επιλογή λίστας προσωπικού", start_dir, "Excel (*.xlsx *.xlsm)")
        if not path:
            return
        try:
            self._load_people(path)
            self.config.personnel_file = path
            self.config.save()
            if self.store:
                self.store.log_admin_action("PERSONNEL_LIST_SELECTED", {"file": path, "people": len(self.people)})
            self._refresh_info()
            QMessageBox.information(self, "Λίστα προσωπικού", f"Επιλέχθηκε λίστα με {len(self.people)} άτομα.\nΘα χρησιμοποιείται αυτόματα στις επόμενες εκκινήσεις.")
        except Exception as exc:
            QMessageBox.critical(self, "Λίστα προσωπικού", f"Δεν ήταν δυνατή η ανάγνωση του αρχείου.\n{exc}")


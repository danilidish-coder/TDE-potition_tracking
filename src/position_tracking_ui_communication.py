"""Asynchronous client heartbeat, session-aware polling and message alarms."""
from __future__ import annotations
import os
import socket
from position_tracking_windows_session import _windows_session_is_active
from position_tracking_common import _clean, format_when
from position_tracking_store import SharedEventStore
from position_tracking_report_text import _escape_html
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


class CommunicationMixin:
    def _sender_payload(self) -> dict:
        officer = self._officer_selected() if hasattr(self, "officer_agms") else None
        if officer:
            return SharedEventStore._person_payload(officer)
        return {
            "computer": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        }


    def _client_worker_labels(self, clients: list[dict]) -> dict[str, str]:
        active_by_computer: dict[str, list[dict]] = {}
        if self.store:
            for item in self.store.active_all():
                active_by_computer.setdefault(_clean(item.get("computer")).upper(), []).append(item)
        labels = {}
        for client in clients:
            cid = _clean(client.get("client_id"))
            computer = _clean(client.get("computer"))
            user = _clean(client.get("user"))
            people = active_by_computer.get(computer.upper(), [])
            worker_text = ""
            if people:
                names = []
                for item in people:
                    name = _clean(
                        f"{item.get('rank','')} {item.get('surname','')} {item.get('given_name','')}"
                    ) or _clean(item.get("full_name"))
                    pos = _clean(item.get("position"))
                    direction = _clean(item.get("direction"))
                    names.append(f"{name} — Θέση {pos} {direction}".strip())
                worker_text = " | " + " / ".join(names)
            labels[cid] = f"{computer} — {user}{worker_text}"
        return labels


    def _communication_io(self, window_state: str):
        """Shared-folder IO must not run on the Qt GUI thread."""
        session_active = _windows_session_is_active()
        # Central closures are owned only by the offline-sync worker.
        # Running an independent heartbeat-side close here could overtake
        # the original unsent END and discard its timestamp/event ID.
        self.store.write_client_heartbeat(self.client_id, {
            "app_started_at": self._app_started_at,
            "window_state": window_state,
            "windows_session_active": session_active,
        })
        online = self.store.online_clients()
        commands = self.store.pending_commands(self.client_id)
        pending = self.store.pending_messages(self.client_id)
        return online, commands, pending


    def _communication_tick(self):
        if getattr(self, "_exit_in_progress", False):
            return
        if not self.store:
            return
        future = self._communication_future
        if future is not None:
            if not future.done():
                return
            self._communication_future = None
            try:
                online, commands, pending = future.result()
                if hasattr(self, "comm_status"):
                    self.comm_status.setText(
                        f"ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ — ενεργοί σταθμοί: {len(online)}"
                    )
            except Exception:
                if hasattr(self, "comm_status"):
                    self.comm_status.setText("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ — ΕΛΕΓΧΟΣ ΣΥΝΔΕΣΗΣ")
                return
            if commands:
                command = commands[0]
                if _clean(command.get("type")).upper() == "CLOSE_APP":
                    self._start_confirmed_exit(_clean(command.get("command_id")))
                    return
            if pending and not self._message_dialog_active:
                self._show_message_alarm(pending[0])
        if self._communication_future is None:
            state = "ΕΛΑΧΙΣΤΟΠΟΙΗΜΕΝΟ" if self.isMinimized() else "ΑΝΟΙΧΤΟ"
            self._communication_future = self._network_pool.submit(
                self._communication_io, state
            )


    def _show_message_alarm(self, message: dict):
        if not self.store:
            return
        self._message_dialog_active = True
        try:
            priority = _clean(message.get("priority")).upper() or "ΟΔΗΓΙΑ"
            sender = message.get("sender") or {}
            sender_name = _clean(
                f"{sender.get('rank','')} {sender.get('surname','')} {sender.get('given_name','')}"
            ) or _clean(sender.get("full_name")) or _clean(sender.get("user")) or "Αξιωματικός Υπηρεσίας"
            created = format_when(message.get("created_at"))
            text_value = _clean(message.get("text"))

            self.showNormal()
            self.raise_()
            self.activateWindow()
            if priority in {"ΟΔΗΓΙΑ", "ΕΠΕΙΓΟΝ"}:
                QApplication.beep()

            box = QMessageBox(self)
            box.setWindowTitle(f"{priority} — ΑΞΙΩΜΑΤΙΚΟΣ ΥΠΗΡΕΣΙΑΣ")
            box.setIcon(QMessageBox.Warning if priority == "ΕΠΕΙΓΟΝ" else QMessageBox.Information)
            box.setText(
                f"<b>{priority}</b><br><br>"
                f"<b>Από:</b> {_escape_html(sender_name)}<br>"
                f"<b>Ώρα:</b> {_escape_html(created)}<br><br>"
                f"{_escape_html(text_value)}"
            )
            box.setStandardButtons(QMessageBox.Ok)
            ack_button = box.button(QMessageBox.Ok)
            if ack_button:
                ack_button.setText("ΕΛΑΒΑ ΓΝΩΣΗ")
                ack_button.setMinimumWidth(180)
                ack_button.setMinimumHeight(44)
            box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            box.exec()
            self.store.acknowledge_message(_clean(message.get("message_id")), self.client_id)
        finally:
            self._message_dialog_active = False


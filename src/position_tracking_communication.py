"""Client heartbeat, messages, acknowledgements and administrative commands."""
from __future__ import annotations
from datetime import datetime, timedelta
import json
import os
import socket
import uuid
from position_tracking_common import _clean, _safe_name


class CommunicationStoreMixin:
    @staticmethod
    def local_client_id() -> str:
        computer = _safe_name(socket.gethostname())
        user = _safe_name(os.environ.get("USERNAME") or os.environ.get("USER") or "USER")
        # Distinguish two Windows sessions/processes sharing the same user.
        return f"{computer}__{user}__{os.getpid()}"


    def write_client_heartbeat(self, client_id: str, extra: dict | None = None) -> dict:
        payload = {
            "client_id": _clean(client_id),
            "computer": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "pid": os.getpid(),
            "last_seen": datetime.now().isoformat(timespec="seconds"),
        }
        if extra:
            payload.update(extra)
        self._atomic_json(self.comm_clients / f"{_safe_name(client_id)}.json", payload)
        return payload


    def remove_client_heartbeat(self, client_id: str):
        (self.comm_clients / f"{_safe_name(client_id)}.json").unlink(missing_ok=True)


    def online_clients(self, max_age_seconds: int = 15) -> list[dict]:
        now = datetime.now()
        result = []
        for path in self.comm_clients.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                seen = datetime.fromisoformat(_clean(data.get("last_seen")))
                if (now - seen).total_seconds() <= max(3, int(max_age_seconds)):
                    result.append(data)
            except Exception:
                continue
        return sorted(result, key=lambda x: (_clean(x.get("computer")), _clean(x.get("user"))))


    def send_message(
        self,
        sender: dict,
        target_client_ids: list[str],
        text: str,
        priority: str = "ΟΔΗΓΙΑ",
        target_label: str = "",
    ) -> dict:
        targets = sorted({_clean(x) for x in target_client_ids if _clean(x)})
        text = _clean(text)
        if not targets:
            raise ValueError("Δεν βρέθηκε ενεργός παραλήπτης.")
        if not text:
            raise ValueError("Γράψτε το μήνυμα / οδηγία.")
        message_id = uuid.uuid4().hex
        payload = {
            "message_id": message_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "sender": sender or {},
            "targets": targets,
            "target_label": _clean(target_label),
            "priority": _clean(priority).upper() or "ΟΔΗΓΙΑ",
            "text": text,
        }
        self._atomic_json(self.comm_messages / f"{message_id}.json", payload)
        self.log_admin_action("MESSAGE_SENT", {
            "message_id": message_id, "targets": targets, "priority": payload["priority"],
            "target_label": payload["target_label"],
        })
        return payload


    def acknowledge_message(self, message_id: str, client_id: str):
        folder = self.comm_acks / _safe_name(message_id)
        payload = {
            "message_id": _clean(message_id),
            "client_id": _clean(client_id),
            "ack_at": datetime.now().isoformat(timespec="seconds"),
            "computer": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        }
        self._atomic_json(folder / f"{_safe_name(client_id)}.json", payload)


    def pending_messages(self, client_id: str, max_age_days: int = 7) -> list[dict]:
        client_id = _clean(client_id)
        cutoff = datetime.now() - timedelta(days=max(1, int(max_age_days)))
        result = []
        for path in sorted(self.comm_messages.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if client_id not in [_clean(x) for x in data.get("targets", [])]:
                    continue
                created = datetime.fromisoformat(_clean(data.get("created_at")))
                if created < cutoff:
                    continue
                ack = self.comm_acks / _safe_name(data.get("message_id")) / f"{_safe_name(client_id)}.json"
                if not ack.exists():
                    result.append(data)
            except Exception:
                continue
        return sorted(result, key=lambda x: _clean(x.get("created_at")))


    def message_acknowledgements(self, message_id: str) -> list[dict]:
        folder = self.comm_acks / _safe_name(message_id)
        result = []
        if folder.exists():
            for path in folder.glob("*.json"):
                try:
                    result.append(json.loads(path.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return result


    def recent_sent_messages(self, limit: int = 20) -> list[dict]:
        result = []
        for path in sorted(self.comm_messages.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["acknowledgements"] = self.message_acknowledgements(_clean(data.get("message_id")))
                result.append(data)
            except Exception:
                continue
            if len(result) >= max(1, int(limit)):
                break
        return result


    def send_close_command(self, sender: dict, target_client_id: str, reason: str = "") -> dict:
        target_client_id = _clean(target_client_id)
        if not target_client_id:
            raise ValueError("Δεν επιλέχθηκε τερματικό.")
        command_id = uuid.uuid4().hex
        payload = {
            "command_id": command_id,
            "type": "CLOSE_APP",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "sender": sender or {},
            "target_client_id": target_client_id,
            "reason": _clean(reason),
        }
        self._atomic_json(self.comm_commands / f"{command_id}.json", payload)
        self.log_admin_action("REMOTE_CLOSE_SENT", {
            "command_id": command_id, "target_client_id": target_client_id, "reason": _clean(reason)
        })
        return payload


    def pending_commands(self, client_id: str) -> list[dict]:
        client_id = _clean(client_id)
        result = []
        for path in sorted(self.comm_commands.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if _clean(data.get("target_client_id")) != client_id:
                    continue
                ack = self.comm_command_acks / f"{_safe_name(data.get('command_id'))}.json"
                if not ack.exists():
                    result.append(data)
            except Exception:
                continue
        return sorted(result, key=lambda x: _clean(x.get("created_at")))


    def acknowledge_command(self, command_id: str, client_id: str):
        payload = {
            "command_id": _clean(command_id),
            "client_id": _clean(client_id),
            "ack_at": datetime.now().isoformat(timespec="seconds"),
            "computer": socket.gethostname(),
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        }
        self._atomic_json(self.comm_command_acks / f"{_safe_name(command_id)}.json", payload)


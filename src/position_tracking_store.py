"""Compose shared storage capabilities and own paths, audit and backup maintenance.

Capability modules operate on this instance's explicit filesystem/SQLite state.
There is no application-entry or Qt dependency; UI/offline callers retain the
same public SharedEventStore API and all receipt/lock order semantics.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import socket
import zipfile
from position_tracking_common import _clean
from position_tracking_store_io import BusyError
from position_tracking_store_io import StoreIOMixin
from position_tracking_communication import CommunicationStoreMixin
from position_tracking_session_index import SessionIndexMixin
from position_tracking_shift_index import ShiftIndexMixin
from position_tracking_positions import PositionStoreMixin
from position_tracking_shifts import ShiftLifecycleMixin
from position_tracking_event_queries import EventQueryMixin
from position_tracking_position_recovery import PositionRecoveryMixin


class SharedEventStore(PositionRecoveryMixin, EventQueryMixin, ShiftLifecycleMixin, PositionStoreMixin, ShiftIndexMixin, SessionIndexMixin, CommunicationStoreMixin, StoreIOMixin):
    def __init__(self, central_root: str | Path):
        root = Path(central_root)
        self.root = root if root.name == ".tde_runtime" else (root if root.name.upper() == "TDE_DATA" else root / "TDE_DATA")
        self.events = self.root / "events"
        self.active = self.root / "active"
        self.locks = self.root / "locks"
        self.reports = self.root / "reports"
        self.shifts = self.root / "shifts"
        self.audit = self.root / "audit"
        self.backups = self.root / "backups"
        self.current_docs = self.root / "current"
        self.archive = self.root / "archive"
        self.statistics = self.root / "statistics"
        self.communications = self.root / "communications"
        self.comm_clients = self.communications / "clients"
        self.comm_messages = self.communications / "messages"
        self.comm_acks = self.communications / "acks"
        self.comm_commands = self.communications / "commands"
        self.comm_command_acks = self.communications / "command_acks"
        self.shift_db = self.root / "shift_reports.sqlite3"
        self.pending_index = self.root / "pending_sessions"
        self.corrections = self.root / "start_corrections"
        for p in (
            self.events, self.active, self.locks, self.reports, self.shifts, self.audit,
            self.backups, self.current_docs, self.archive, self.statistics,
            self.communications, self.comm_clients, self.comm_messages, self.comm_acks,
            self.comm_commands, self.comm_command_acks, self.pending_index, self.corrections,
        ):
            p.mkdir(parents=True, exist_ok=True)
        self._init_shift_db()
        self._init_position_recovery()
        # Recover END events left unindexed after a process or SQLite interruption.
        try:
            self.reconcile_pending_sessions()
        except Exception:
            pass


    def log_admin_action(self, action: str, details: dict | None = None) -> Path:
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "action": _clean(action),
            "details": details or {},
            "user": os.environ.get("USERNAME") or os.environ.get("USER") or "",
            "computer": socket.gethostname(),
        }
        path = self.audit / "admin_audit.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def backup_data(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = self.backups / f"TDE_DATA_BACKUP_{stamp}.zip"
        temp = target.with_suffix(target.suffix + ".tmp")
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in self.root.rglob("*"):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.root)
                except Exception:
                    continue
                if rel.parts and rel.parts[0].lower() == "backups":
                    continue
                zf.write(path, arcname=str(rel))
        os.replace(temp, target)
        self.log_admin_action("BACKUP_CREATED", {"file": str(target)})
        return target

    def finalize_shift(self, shift: dict, report_text: str = "") -> dict:
        shift_id = _clean(shift.get("shift_id"))
        if not shift_id:
            raise ValueError("Μη έγκυρη βάρδια.")
        current = self.get_shift(shift_id)
        if not current:
            raise ValueError("Δεν βρέθηκε η βάρδια για οριστικοποίηση.")
        if _clean(current.get("status")).upper() == "FINALIZED":
            return current
        current["status"] = "FINALIZED"
        current["finalized_at"] = datetime.now().isoformat(timespec="seconds")
        current["finalized_by"] = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        current["finalized_computer"] = socket.gethostname()
        if report_text:
            current["final_report_text"] = report_text
            current["final_report_sha256"] = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
        self._store_shift_snapshot(current)
        self.log_admin_action("SHIFT_FINALIZED", {"shift_id": shift_id, "people": len(current.get("agms", []))})
        return current


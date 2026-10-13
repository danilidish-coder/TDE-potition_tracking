"""Durable local outbox for the portable Position Tracking EXE.

A pending offline booth claim is provisional; isolated machines CANNOT prove
that no other station chose the same booth. Conflicts remain visible and are
never silently overwritten during replay.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager


class OfflineConflict(RuntimeError):
    pass


class OfflineJournal:
    def __init__(self, directory: str | Path):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "position_outbox.sqlite3"
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, agms TEXT NOT NULL,
                position TEXT NOT NULL, direction TEXT NOT NULL,
                created_at TEXT NOT NULL, payload TEXT NOT NULL,
                start_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'PENDING',
                error TEXT NOT NULL DEFAULT '', recorded_at TEXT NOT NULL DEFAULT ''
            )""")
            db.execute("""CREATE INDEX IF NOT EXISTS op_status ON operations(status, rowid)""".replace(", rowid", ", created_at"))
            db.execute("""CREATE TABLE IF NOT EXISTS observed (
                agms TEXT PRIMARY KEY, record TEXT NOT NULL, checked_at TEXT NOT NULL
            )""")

    @contextmanager
    def _db(self):
        """Always close SQLite handles; sqlite3.Connection.__exit__ alone does not close them on Windows."""
        db = sqlite3.connect(self.path, timeout=2.0)
        try:
            db.execute("PRAGMA busy_timeout = 2000")
            db.execute("PRAGMA synchronous = FULL")
            # Local machine queue uses rollback journaling. Setting WAL mode on
            # each startup races with other booth processes and produces SQLITE_BUSY.
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _payload(person, client_id):
        return {"agms": person.agms, "rank": person.rank,
                "surname": person.surname, "given_name": person.given_name,
                "client_id": client_id, "computer": socket.gethostname(),
                "windows_user": os.environ.get("USERNAME") or os.environ.get("USER") or ""}

    def remember(self, agms: str, active: dict | None):
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO observed VALUES(?,?,?)",
                       (agms, json.dumps(active, ensure_ascii=False), datetime.now().isoformat()))

    @staticmethod
    def _rows_db(db, statuses=("PENDING", "CONFLICT")):
        q = ",".join("?" for _ in statuses)
        rows = db.execute(f"SELECT id, kind, agms, position, direction, created_at, payload, start_id, status, error FROM operations WHERE status IN ({q}) ORDER BY rowid", tuple(statuses)).fetchall()
        return [dict(zip(("id", "kind", "agms", "position", "direction", "created_at", "payload", "start_id", "status", "error"), row)) for row in rows]

    def _rows(self, statuses=("PENDING", "CONFLICT")):
        with self._db() as db:
            return self._rows_db(db, statuses)

    def pending_count(self):
        return len(self._rows())

    def conflicts(self):
        return self._rows(("CONFLICT",))

    @staticmethod
    def _local_active_db(db, agms: str, pending=None):
        row = db.execute("SELECT record FROM observed WHERE agms=?", (agms,)).fetchone()
        item = json.loads(row[0]) if row else None
        if pending is None:
            pending = OfflineJournal._rows_db(db)
        for op in pending:
            if op["agms"] != agms:
                continue
            if op["kind"] == "START":
                p = json.loads(op["payload"])
                item = {**p, "event_id": op["id"], "timestamp": op["created_at"],
                        "position": op["position"], "direction": op["direction"],
                        "offline_status": op["status"]}
            elif op["kind"] == "END" and item and item.get("event_id") == op["start_id"]:
                item = None
        return item

    def local_active(self, agms: str):
        with self._db() as db:
            return self._local_active_db(db, agms)

    def auto_close_previous_windows_users(self, computer: str, windows_user: str):
        """On next Windows user launch, durably queue END for previous users.

        Works across logoffs because the outbox lives in the machine's public
        writable directory. A lock screen with no new login does nothing.
        """
        computer = (computer or "").casefold()
        windows_user = (windows_user or "").casefold()
        if not computer or not windows_user:
            return []
        with self._db() as db:
            rows = db.execute("SELECT agms FROM observed").fetchall()
        candidates = {row[0] for row in rows}
        candidates.update(x["agms"] for x in self._rows())
        closed = []
        for agms in candidates:
            rec = self.local_active(agms)
            if not rec:
                continue
            if (rec.get("computer") or "").casefold() != computer:
                continue
            prior_user = (rec.get("user") or rec.get("windows_user") or "").casefold()
            if not prior_user or prior_user == windows_user:
                continue
            class Person:
                pass
            person = Person()
            person.agms = agms
            person.rank = rec.get("rank", "")
            person.surname = rec.get("surname", "")
            person.given_name = rec.get("given_name", "")
            op = self.enqueue("END", person, client_id="AUTO_WINDOWS_USER_HANDOFF", reason="WINDOWS_USER_HANDOFF_OFFLINE")
            closed.append(op["operation_id"])
        return closed

    def enqueue(self, kind, person, position="", direction="", client_id="", reason=""):
        if kind not in ("START", "END"):
            raise ValueError("Invalid event kind")
        # Atomic check+insert protects against independent GUI processes on the
        # same booth claiming the same place while the central host is offline.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = self._rows_db(db)
            if any(x["status"] == "CONFLICT" for x in pending):
                raise OfflineConflict("Υπάρχει ΑΣΥΜΦΩΝΙΑ συγχρονισμού. Απαιτείται έλεγχος ΑΞΥΠ πριν από νέες ενέργειες.")
            if kind == "START":
                if self._local_active_db(db, person.agms, pending):
                    raise ValueError("Ο αστυνομικός έχει ήδη ανοικτή θέση.")
                for x in pending:
                    if x["kind"] == "START" and x["position"] == position and (self._local_active_db(db, x["agms"], pending) or {}).get("event_id") == x["id"]:
                        raise ValueError("Η θέση είναι ήδη δεσμευμένη τοπικά.")
                if not position or direction not in ("ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"):
                    raise ValueError("Επιλέξτε έγκυρη θέση και κατεύθυνση.")
                start_ref = ""
            else:
                current = self._local_active_db(db, person.agms, pending)
                if not current:
                    raise ValueError("Δεν υπάρχει γνωστή ενεργή θέση για αυτόν τον αστυνομικό.")
                position = current.get("position", "")
                direction = current.get("direction", "")
                start_ref = current.get("event_id", "")
                if not start_ref:
                    raise ValueError("Η ενεργή θέση δεν διαθέτει ασφαλές αναγνωριστικό έναρξης.")
            op_id = uuid.uuid4().hex
            created = datetime.now().isoformat(timespec="seconds")
            data = self._payload(person, client_id)
            if reason:
                data["reason"] = reason
            db.execute("INSERT INTO operations(id,kind,agms,position,direction,created_at,payload,start_id) VALUES(?,?,?,?,?,?,?,?)",
                       (op_id, kind, person.agms, position, direction, created,
                        json.dumps(data, ensure_ascii=False), start_ref))
        return {"operation_id": op_id, "kind": kind, "timestamp": created,
                "position": position, "direction": direction, "pending_sync": True}

    def sync(self, store, person_type):
        """Replay in recorded order, exactly identified by operation IDs.

        Returns pending and conflict counts; stops on network failure. Pending
        operations remain durable and retryable across process termination.
        """
        applied = []
        if self.conflicts():
            return {"applied": [], "pending": self.pending_count(), "conflicts": self.conflicts()}
        for op in self._rows(("PENDING",)):
            p = json.loads(op["payload"])
            person = person_type(agms=p["agms"], rank=p["rank"], surname=p["surname"], given_name=p["given_name"])
            try:
                if op["kind"] == "START":
                    event = store.start(person, op["position"], op["direction"],
                                        when=datetime.fromisoformat(op["created_at"]),
                                        client_id=p["client_id"], event_id=op["id"],
                                        origin_computer=p["computer"], origin_user=p["windows_user"])
                else:
                    event = store.end(person, when=datetime.fromisoformat(op["created_at"]),
                                      expected_start_event_id=op["start_id"],
                                      end_reason=p.get("reason") or "OFFLINE_REPLAY", event_id=op["id"],
                                      origin_computer=p["computer"], origin_user=p["windows_user"])
            except ValueError as exc:
                self._mark(op["id"], "CONFLICT", str(exc))
                break
            except Exception as exc:
                # Network outage, corrupt file or lock contention: never
                # discard an operation or claim that it was applied.
                if "άλλαξε" in str(exc) or "changed" in str(exc).lower():
                    self._mark(op["id"], "CONFLICT", str(exc))
                break
            self._mark(op["id"], "APPLIED", "")
            applied.append(op["id"])
            if op["kind"] == "START":
                self.remember(op["agms"], event)
            else:
                self.remember(op["agms"], None)
        return {"applied": applied, "pending": self.pending_count(), "conflicts": self.conflicts()}

    def resolve_conflict(self, op_id: str, officer_agms: str, reason: str):
        """Reject an unconfirmed offline claim with a durable officer audit.

        Never remove historical records. Dependent unsent END records also
        cannot be replayed after their START has been rejected.
        """
        if not officer_agms.strip() or len(reason.strip()) < 8:
            raise ValueError("Απαιτείται ΑΓΜΣ ΑΞΥΠ και αιτιολογία τουλάχιστον 8 χαρακτήρων.")
        with self._db() as db:
            row = db.execute("SELECT kind,status FROM operations WHERE id=?", (op_id,)).fetchone()
            if not row or row[1] != "CONFLICT":
                raise ValueError("Η ασυμφωνία έχει ήδη επιλυθεί ή άλλαξε κατάσταση.")
            note = f"ΑΞΥΠ {officer_agms}: {reason.strip()}"
            dt = datetime.now().isoformat(timespec="seconds")
            db.execute("UPDATE operations SET status='REJECTED',error=?,recorded_at=? WHERE id=?", (note, dt, op_id))
            if row[0] == "START":
                db.execute("UPDATE operations SET status='REJECTED',error=?,recorded_at=? WHERE start_id=? AND status IN ('PENDING','CONFLICT')", (note + " (dependent END)", dt, op_id))
        return True

    def _mark(self, ident, state, error):
        with self._db() as db:
            db.execute("UPDATE operations SET status=?, error=?, recorded_at=? WHERE id=?",
                       (state, error, datetime.now().isoformat(timespec="seconds"), ident))

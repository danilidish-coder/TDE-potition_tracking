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
            if not op.get("already_recorded"):
                closed.append(op["operation_id"])
        return closed

    @staticmethod
    def _prior_handoff_end_db(db, agms: str, exact_start_id: str):
        """A prior automatic END is a durable one-shot claim for this START.

        REJECTED is intentionally included. A dismissed stale END must NEVER
        be regenerated when a third/fourth Windows account logs onto the booth.
        """
        if not exact_start_id:
            return None
        for ident, payload, status in db.execute(
            "SELECT id, payload, status FROM operations "
            "WHERE agms=? AND kind='END' AND start_id=? ORDER BY rowid DESC",
            (agms, exact_start_id),
        ).fetchall():
            try:
                if json.loads(payload).get("reason") == "WINDOWS_USER_HANDOFF_OFFLINE":
                    return (ident, status)
            except (TypeError, ValueError):
                continue
        return None

    def enqueue(self, kind, person, position="", direction="", client_id="", reason=""):
        if kind not in ("START", "END"):
            raise ValueError("Invalid event kind")
        # Atomic check+insert protects against independent GUI processes on the
        # same booth claiming the same place while the central host is offline.
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = self._rows_db(db)
            if kind == "END" and reason == "WINDOWS_USER_HANDOFF_OFFLINE":
                # Look through *all* historical statuses, not only PENDING.
                # The exact same old START can be retried after a user manually
                # rejects the handoff. Serialize through BEGIN IMMEDIATE to
                # prevent simultaneous Windows logins queuing duplicates.
                recorded = self._local_active_db(db, person.agms, pending)
                if recorded:
                    original_start = recorded.get("event_id", "")
                    prior = self._prior_handoff_end_db(db, person.agms, original_start)
                    if prior is not None:
                        return {
                            "operation_id": prior[0], "kind": kind,
                            "position": recorded.get("position", ""),
                            "direction": recorded.get("direction", ""),
                            "pending_sync": prior[1] in ("PENDING", "CONFLICT"),
                            "already_recorded": True,
                        }
            # A conflict on another officer or booth must not stop all work
            # at this Windows terminal. Keep the affected officer/booth guarded.
            conflicts = [x for x in pending if x["status"] == "CONFLICT"]
            if any(x["agms"] == person.agms for x in conflicts) or (
                kind == "START" and any(
                    x["kind"] == "START" and x["position"] == position
                    for x in conflicts
                )
            ):
                raise OfflineConflict("Υπάρχει ΑΣΥΜΦΩΝΙΑ για τον αστυνομικό ή τη θέση. Απαιτείται έλεγχος ΑΞΥΠ.")
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

    @staticmethod
    def _is_handoff_end(op):
        if op["kind"] != "END":
            return False
        return json.loads(op["payload"]).get("reason") == "WINDOWS_USER_HANDOFF_OFFLINE"

    def _reconcile_stale_handoff(self, store, op):
        """Safely retire a handoff END if its exact START is no longer active.

        The prior officer may already have moved to a different terminal and
        opened another session. Never issue END against that replacement.
        This also repairs CONFLICT rows left by v1.2.5 after a restart.
        """
        if not self._is_handoff_end(op):
            return False
        current = store.get_active(op["agms"])
        if current and current.get("event_id") == op["start_id"]:
            return False
        # Auditable reconciliation on the central share *before* clearing the
        # local conflict. Do not assert that an END event was written.
        store._atomic_json(
            store.audit / "offline_handoff_reconciliations" / (op["id"] + ".json"),
            {
                "action": "OFFLINE_HANDOFF_END_ALREADY_SUPERSEDED",
                "operation_id": op["id"],
                "agms": op["agms"],
                "old_start_event_id": op["start_id"],
                "old_position": op["position"],
                "old_created_at": op["created_at"],
                "current_start_event_id": (current or {}).get("event_id", ""),
                "current_position": (current or {}).get("position", ""),
                "note": "Obsolete automatic handoff END: replacement session preserved; actual departure time unverified",
            },
        )
        self._mark(op["id"], "RECONCILED", "Η παλιά θέση δεν είναι πλέον ενεργή. Η νέα θέση διατηρήθηκε. Έγινε καταγραφή ελέγχου.")
        self.remember(op["agms"], current)
        return True

    def _refresh_rejected_handoff_observations(self, store):
        """Replace a stale local cache only after checking the central START.

        A supervisor rejecting an old auto-END preserves the row for audit,
        but older versions left the old START in 'observed' indefinitely.
        The next login would then generate another END. When the central
        system proves that the old START is no longer active, retire the old
        local cache without creating a false END or disturbing a new session.
        """
        for op in self._rows(("REJECTED",)):
            if not self._is_handoff_end(op) or not op["start_id"]:
                continue
            with self._db() as db:
                row = db.execute("SELECT record FROM observed WHERE agms=?", (op["agms"],)).fetchone()
            if not row:
                continue
            try:
                cached = json.loads(row[0])
            except (TypeError, ValueError):
                continue
            if not cached or cached.get("event_id") != op["start_id"]:
                continue
            # Failure to read central state is NOT proof of a closed session.
            current = store.get_active(op["agms"])
            if current and current.get("event_id") == op["start_id"]:
                continue
            store._atomic_json(
                store.audit / "offline_handoff_reconciliations" / (op["id"] + "_rejected_cache.json"),
                {
                    "action": "REJECTED_OLD_HANDOFF_LOCAL_CACHE_REFRESH",
                    "operation_id": op["id"], "agms": op["agms"],
                    "old_start_event_id": op["start_id"],
                    "old_position": op["position"],
                    "current_start_event_id": (current or {}).get("event_id", ""),
                    "current_position": (current or {}).get("position", ""),
                    "note": "Local cache updated after verified central read; "
                            "no END operation was created and replacement START was preserved",
                },
            )
            with self._db() as db:
                # CAS: an unrelated update or another Windows user must not be
                # overwritten by a late network reply.
                latest = db.execute("SELECT record FROM observed WHERE agms=?", (op["agms"],)).fetchone()
                if latest and latest[0] == row[0]:
                    db.execute(
                        "UPDATE observed SET record=?, checked_at=? WHERE agms=? AND record=?",
                        (json.dumps(current, ensure_ascii=False),
                         datetime.now().isoformat(), op["agms"], row[0]),
                    )

    def _reconcile_superseded_handoff_start(self, store, op):
        """Preserve a complete locally recorded OLD session as a central
        reconciliation record if its START never arrived but its officer has
        a newer, different active START elsewhere. Never alter that new START.
        """
        if op["kind"] != "START":
            return False
        dependent = [
            x for x in self._rows(("PENDING", "CONFLICT"))
            if x["kind"] == "END" and x["start_id"] == op["id"]
            and self._is_handoff_end(x)
        ]
        if not dependent:
            return False  # May still be physically working; do not infer END.
        current = store.get_active(op["agms"])
        if not current or current.get("event_id") == op["id"]:
            return False
        try:
            if datetime.fromisoformat(current["timestamp"]) <= datetime.fromisoformat(op["created_at"]):
                return False
        except (KeyError, ValueError, TypeError):
            return False  # An uncertain timeline requires manual reconciliation.
        record = {
            "action": "SUPERSEDED_OFFLINE_HANDOFF_SESSION_UNVERIFIED",
            "agms": op["agms"], "old_start_operation_id": op["id"],
            "old_start_at": op["created_at"], "old_position": op["position"],
            "old_end_operations": [
                {"id": x["id"], "recorded_at": x["created_at"]}
                for x in dependent
            ],
            "current_active_start_id": current.get("event_id"),
            "current_active_position": current.get("position"),
            "note": "Locally recorded earlier START/automatic END archived for supervisor review; exact departure time not verified; replacement START untouched",
        }
        # Commit audit to central SMB first. If unavailable, retain all
        # local operations for a later attempt.
        store._atomic_json(
            store.audit / "offline_handoff_reconciliations" / (op["id"] + ".json"),
            record,
        )
        note = "Αρχειοθετήθηκε τοπική παλιά θέση για έλεγχο ΑΞΥΠ. Η νέα θέση διατηρήθηκε."
        when = datetime.now().isoformat(timespec="seconds")
        ids = [op["id"]] + [x["id"] for x in dependent]
        with self._db() as db:
            for ident in ids:
                db.execute(
                    "UPDATE operations SET status='RECONCILED',error=?,recorded_at=? "
                    "WHERE id=? AND status IN ('PENDING','CONFLICT')",
                    (note, when, ident),
                )
            db.execute(
                "INSERT OR REPLACE INTO observed VALUES(?,?,?)",
                (op["agms"], json.dumps(current, ensure_ascii=False), when),
            )
        return True

    def sync(self, store, person_type):
        """Replay durable local events independently unless their officer or
        claimed booth conflicts. Persist conflicts; never discard work silently.
        """
        applied = []
        # Repair previously stuck v1.2.5 handoffs before processing new claims.
        for op in self._rows(("CONFLICT",)):
            try:
                if (self._reconcile_superseded_handoff_start(store, op)
                        or self._reconcile_stale_handoff(store, op)):
                    applied.append(op["id"])
            except Exception:
                # If the central host/audit is unreachable, retain the local
                # conflict and let the next timed sync retry it.
                pass
        blocked = self.conflicts()
        blocked_agms = {x["agms"] for x in blocked}
        blocked_positions = {x["position"] for x in blocked if x["kind"] == "START"}
        network_error = ""
        for op in self._rows(("PENDING",)):
            # Previous reconciliation can atomically settle dependent operations
            # that were present in this iteration's original snapshot.
            with self._db() as db:
                still_pending = db.execute(
                    "SELECT status FROM operations WHERE id=?", (op["id"],)
                ).fetchone()
            if not still_pending or still_pending[0] != "PENDING":
                continue
            if op["agms"] in blocked_agms or (
                op["kind"] == "START" and op["position"] in blocked_positions
            ):
                continue
            p = json.loads(op["payload"])
            person = person_type(agms=p["agms"], rank=p["rank"], surname=p["surname"], given_name=p["given_name"])
            try:
                if (self._reconcile_superseded_handoff_start(store, op)
                        or self._reconcile_stale_handoff(store, op)):
                    applied.append(op["id"])
                    continue
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
                blocked_agms.add(op["agms"])
                if op["kind"] == "START":
                    blocked_positions.add(op["position"])
                continue
            except Exception as exc:
                # Network failure/lock contention: never discard or acknowledge
                # any unsent entry. Conflicts are isolated by AGMS/booth.
                if "άλλαξε" in str(exc) or "changed" in str(exc).lower():
                    self._mark(op["id"], "CONFLICT", str(exc))
                    blocked_agms.add(op["agms"])
                    if op["kind"] == "START":
                        blocked_positions.add(op["position"])
                    continue
                network_error = str(exc)[:240]
                break
            self._mark(op["id"], "APPLIED", "")
            applied.append(op["id"])
            if op["kind"] == "START":
                self.remember(op["agms"], event)
            else:
                self.remember(op["agms"], None)
        if not network_error:
            # This is a network worker, never the Qt UI thread. Refresh only
            # old rejected END caches that have not already been corrected.
            try:
                self._refresh_rejected_handoff_observations(store)
            except Exception as exc:
                # Do not discard local entries or break new officers' replay
                # because the central share was temporarily unavailable.
                network_error = str(exc)[:240]
        return {"applied": applied, "pending": self.pending_count(), "conflicts": self.conflicts(), "network_error": network_error}

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

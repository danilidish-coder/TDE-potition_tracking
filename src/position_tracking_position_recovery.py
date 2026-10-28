"""Central-only operation index and bounded recovery of immutable event files.

The JSON event supplies immutable evidence. SQLite records its location BEFORE
the write and atomically accepts its token/live claim, so a superseded worker's
later JSON write cannot regain authority. No local queue is used.
All callers hold __POSITION_TRANSACTIONS__, then any per-person locks.
"""
from datetime import datetime
from contextlib import contextmanager
import json
import os
from pathlib import Path
from itertools import islice
import re
import uuid

from position_tracking_common import _clean
from position_tracking_store_io import BusyError


class PositionRecoveryMixin:
    LEGACY_RECOVERY_FILE_LIMIT = 20000
    POSITION_RECOVERY_LIMIT = 256

    @contextmanager
    def _position_transaction(self, agms):
        with self.officer_lock("__POSITION_TRANSACTIONS__"):
            self._recover_position_operations_locked()
            with self.officer_lock(agms):
                yield

    def _position_rows(self, sql, args=()):
        with self._shift_db_connect() as db:
            return [dict(row) for row in db.execute(sql, args).fetchall()]

    def _position_index_write(self, sql, args=()):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as db:
                return db.execute(sql, args).rowcount

    def _event_path(self, event):
        ident = event.get("event_id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ident):
            raise BusyError("Μη έγκυρο αναγνωριστικό κεντρικής καταχώρισης.")
        when = datetime.fromisoformat(event["timestamp"])
        return (self.events / f"{when:%Y}" / f"{when:%m}" / f"{when:%Y-%m-%d}" /
                f"{when:%Y%m%d_%H%M%S_%f}_{ident}.json")

    @staticmethod
    def _event_payload(event):
        # event_file is an old, optional materialization detail, not identity.
        return {key: value for key, value in event.items() if key != "event_file"}

    def _position_evidence(self, row):
        if row.get('handover_id') and row['state'] == 'COMMITTED':
            return self._handover_evidence(row)
        path = self.root / row["event_path"]
        try:
            event = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            if row["state"] == "COMMITTED":
                raise BusyError("Λείπει επιβεβαιωμένη κεντρική καταχώριση. Απαιτείται έλεγχος.")
            # A missing parent after an SMB outage is not proof of noncommit.
            path.parent.stat()
            return None
        if self._event_payload(event) != json.loads(row["payload"]):
            raise BusyError("Ασυμφωνία αμετάβλητης κεντρικής καταχώρισης.")
        return event

    def _position_operation(self, event_id):
        rows = self._position_rows("SELECT * FROM position_operations WHERE event_id=?", (event_id,))
        return rows[0] if rows else None

    def _committed_position_operation(self, event_id):
        row = self._position_operation(event_id)
        if not row or row["state"] != "COMMITTED":
            return None
        return self._position_evidence(row)

    def _committed_position_end(self, start_id):
        rows = self._position_rows(
            "SELECT * FROM position_operations WHERE start_id=? AND kind='END' AND state='COMMITTED'",
            (start_id,))
        return self._position_evidence(rows[0]) if rows else None

    def _prepare_position_event(self, event):
        attempt = uuid.uuid4().hex
        previous = self._position_operation(event["event_id"])
        if previous:
            original = json.loads(previous["payload"])
            keys = ("kind", "agms", "position", "direction", "start_event_id")
            if any(original.get(key) != event.get(key) for key in keys):
                raise BusyError("Το αναγνωριστικό χρησιμοποιείται από διαφορετική καταχώριση.")
            # Even a precommit retry keeps the originally assigned time/actor.
            event.clear()
            event.update(original)
            self._position_index_write(
                "UPDATE position_operations SET state='PREPARED', settled=0,attempt=? WHERE event_id=? AND state='ABORTED' AND attempt=?",
                (attempt, event["event_id"], previous["attempt"]))
            # Never borrow a competing worker's token if this CAS lost.
            return self.root / previous["event_path"], attempt
        path = self._event_path(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._position_index_write(
            "INSERT INTO position_operations (event_id,kind,agms,start_id,event_path,payload,state,settled,attempt) VALUES (?, ?, ?, ?, ?, ?, 'PREPARED', 0, ?)",
            (event["event_id"], event["kind"], event["agms"], event.get("start_event_id"),
             str(path.relative_to(self.root)), json.dumps(self._event_payload(event), ensure_ascii=False),attempt))
        return path, attempt

    def _settle_position_event(self, event_id):
        self._position_index_write(
            "UPDATE position_operations SET settled=1 WHERE event_id=? AND state='COMMITTED'", (event_id,))

    def _abort_position_event(self, event_id, attempt=None):
        return self._abort_position_attempt(event_id, attempt)

    def _init_position_recovery(self):
        with self.officer_lock("__POSITION_TRANSACTIONS__"):
            with self._shift_db_write_lock():
                with self._shift_db_connect() as db:
                    db.execute("""CREATE TABLE IF NOT EXISTS position_operations (
                        event_id TEXT PRIMARY KEY, kind TEXT NOT NULL, agms TEXT NOT NULL,
                        start_id TEXT, event_path TEXT NOT NULL, payload TEXT NOT NULL,
                        state TEXT NOT NULL, settled INTEGER NOT NULL)""")
                    db.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_end_per_start
                        ON position_operations(start_id) WHERE kind='END' AND state<>'ABORTED'""")
                    db.execute("CREATE INDEX IF NOT EXISTS position_unsettled ON position_operations(settled)")
                    migrated = db.execute("SELECT value FROM meta WHERE key='position_events_index_v1'").fetchone()
                    # Columns must exist before either legacy insert or a retry.
                    columns = {r['name'] for r in db.execute('PRAGMA table_info(position_operations)')}
                    if 'attempt' not in columns:
                        db.execute("ALTER TABLE position_operations ADD COLUMN attempt TEXT NOT NULL DEFAULT ''")
                    if not migrated:
                        self._index_legacy_position_events(db)
                        db.execute("INSERT INTO meta VALUES ('position_events_index_v1', '1')")
                    self._init_position_claims(db, rebuild=not migrated)
                    self._init_handovers(db)
                    self._init_officer_ledger(db)
            self._handover_ready = True
            self._officer_ledger_ready = True
            self._recover_position_operations_locked()

    def _index_legacy_position_events(self, db):
        # One-time, bounded, fail-closed import for an isolated candidate share.
        # A legacy EXE must never write concurrently into this candidate store.
        count = 0
        folders = [self.events]
        while folders:
            with os.scandir(folders.pop()) as entries:
                for entry in entries:
                    count += 1
                    if count > self.LEGACY_RECOVERY_FILE_LIMIT:
                        raise BusyError("Υπέρβαση ορίου αρχικού ελέγχου ιστορικού. Απαιτείται ελεγχόμενη εισαγωγή.")
                    if entry.is_dir(follow_symlinks=False):
                        folders.append(Path(entry.path))
                        continue
                    if not entry.name.endswith(".json"):
                        continue
                    self._index_legacy_position_event(db, Path(entry.path))
        # Already indexed historical sessions need no projection work. Raw
        # unmatched events remain unsettled and must be validated, never hidden.
        db.execute("""UPDATE position_operations SET settled=1 WHERE event_id IN (
            SELECT start_event_id FROM personnel_sessions UNION SELECT end_event_id FROM personnel_sessions)""")

    def _index_legacy_position_event(self, db, path):
        event = json.loads(path.read_text(encoding="utf-8"))
        if event.get("kind") not in ("START", "END"):
            return
        self._event_path(event)  # Validate identity/timestamp, keep original path.
        db.execute("INSERT INTO position_operations (event_id,kind,agms,start_id,event_path,payload,state,settled) VALUES (?, ?, ?, ?, ?, ?, 'COMMITTED', 0)",
                   (event["event_id"], event["kind"], event["agms"], event.get("start_event_id"),
                    str(path.relative_to(self.root)), json.dumps(self._event_payload(event), ensure_ascii=False)))

    def _recover_position_operations_locked(self):
        self._recover_handovers()
        # Older central pending receipts are durable evidence too. Import them
        # before considering a booth free, without relying on an active marker.
        receipts = list(islice(self.pending_index.glob("*.json"), self.POSITION_RECOVERY_LIMIT + 1))
        if len(receipts) > self.POSITION_RECOVERY_LIMIT:
            raise BusyError("Υπέρβαση ορίου κεντρικών αποδείξεων ΛΗΞΗΣ.")
        for path in receipts:
            receipt = json.loads(path.read_text(encoding="utf-8"))
            start, end = receipt["start"], receipt["end"]
            if not self._committed_position_operation(end["event_id"]):
                if end.get("start_event_id") != start.get("event_id") or end.get("agms") != start.get("agms"):
                    raise BusyError("Ασυμφωνία κεντρικής απόδειξης ΛΗΞΗΣ.")
                self._write_event(dict(end))
        rows = self._position_rows(
            "SELECT * FROM position_operations WHERE settled=0 ORDER BY kind LIMIT ?",
            (self.POSITION_RECOVERY_LIMIT + 1,))
        if len(rows) > self.POSITION_RECOVERY_LIMIT:
            raise BusyError("Υπέρβαση ορίου ανάκαμψης θέσεων. Δεν επιτρέπονται νέες καταχωρίσεις.")
        # Resolve commit evidence first, including an END whose ACK was lost.
        committed = []
        for row in rows:
            event = self._position_evidence(row)
            if event is None:
                self._abort_position_event(row["event_id"], row["attempt"])
            else:
                if self._commit_position_attempt(row["event_id"], row["attempt"]):
                    committed.append(event)
        # END sorts before START, so recovery never resurrects a completed START.
        for event in committed:
            with self.officer_lock(event["agms"]):
                if event["kind"] == "END":
                    start = self._committed_position_operation(event["start_event_id"])
                    if not start or start.get("kind") != "START" or start["agms"] != event["agms"]:
                        raise BusyError("Η ΛΗΞΗ δεν αντιστοιχεί σε επιβεβαιωμένη ΕΝΑΡΞΗ.")
                    start = self._apply_start_correction(start)
                    if datetime.fromisoformat(event["timestamp"]) < datetime.fromisoformat(start["timestamp"]):
                        raise BusyError("Η ΛΗΞΗ προηγείται της ΕΝΑΡΞΗΣ. Απαιτείται έλεγχος.")
                    path = self._active_path(event["agms"])
                    try:
                        active = json.loads(path.read_text(encoding="utf-8"))
                    except FileNotFoundError:
                        self.active.stat()
                    else:
                        if active.get("event_id") == start["event_id"]:
                            path.unlink()
                    try:
                        self._store_personnel_session(start, event)
                    except Exception:
                        # The immutable END already releases the booth. Keep
                        # this operation unsettled for another indexing attempt;
                        # report-index availability must not trap live workers.
                        continue
                    receipt = self.pending_index / f"{start['event_id']}.json"
                    receipt.unlink(missing_ok=True)
                elif not self._committed_position_end(event["event_id"]):
                    current = self.get_active(event["agms"])
                    if current and current.get("event_id") != event["event_id"]:
                        raise BusyError("Σύγκρουση δύο ΕΝΑΡΞΕΩΝ για το ίδιο ΑΓΜΣ.")
                    occupied = [item for item in self.active_all()
                                if item.get("position") == event["position"] and item.get("agms") != event["agms"]]
                    if occupied:
                        raise BusyError("Σύγκρουση κεντρικών καταχωρίσεων στην ίδια φυσική θέση.")
                    if not current:
                        self._atomic_json(self._active_path(event["agms"]), event)
                self._settle_position_event(event["event_id"])

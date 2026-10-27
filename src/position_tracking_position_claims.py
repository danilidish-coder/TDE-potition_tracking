"""Transactional central claims; stale JSON projections never own a booth.

SQLite BEGIN IMMEDIATE and UNIQUE constraints form the mutation boundary.
Each prepared attempt has a fresh token; a superseded worker cannot publish
under a retry's token. JSON event bytes remain immutable evidence, but only an
accepted central operation may supply live/report state.
"""
import json
import sqlite3
from position_tracking_store_io import BusyError


class PositionClaimsMixin:
    def _init_position_claims(self, db, rebuild=False):
        columns = {row["name"] for row in db.execute("PRAGMA table_info(position_operations)")}
        if "attempt" not in columns:
            db.execute("ALTER TABLE position_operations ADD COLUMN attempt TEXT NOT NULL DEFAULT ''")
        db.execute("""CREATE TABLE IF NOT EXISTS position_live (
            agms TEXT PRIMARY KEY, position TEXT NOT NULL UNIQUE,
            start_id TEXT NOT NULL UNIQUE)""")
        ready = db.execute("SELECT value FROM meta WHERE key='position_claims_v1'").fetchone()
        if not ready or rebuild:
            db.execute("DELETE FROM position_live")
            try:
                db.execute("""INSERT INTO position_live SELECT agms,
                    json_extract(payload, '$.position'), event_id FROM position_operations s
                    WHERE kind='START' AND state='COMMITTED' AND NOT EXISTS (
                        SELECT 1 FROM position_operations e WHERE e.kind='END'
                        AND e.state='COMMITTED' AND e.start_id=s.event_id)""")
            except sqlite3.IntegrityError as error:
                raise BusyError("Σύγκρουση επιβεβαιωμένων ΕΝΑΡΞΕΩΝ στην κεντρική κατοχή θέσεων.") from error
            db.execute("INSERT OR REPLACE INTO meta VALUES ('position_claims_v1', '1')")

    def _commit_position_attempt(self, event_id, attempt):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM position_operations WHERE event_id=?", (event_id,)).fetchone()
                if not row or row["attempt"] != attempt or row["state"] == "ABORTED":
                    return False
                if row["state"] == "COMMITTED":
                    return True
                event = json.loads(row["payload"])
                if event["kind"] == "START":
                    conflict = db.execute("SELECT 1 FROM position_live WHERE agms=? OR position=?",
                                          (event["agms"], event["position"])).fetchone()
                    if conflict:
                        db.execute("UPDATE position_operations SET state='ABORTED',settled=1 WHERE event_id=?",
                                   (event_id,))
                        return False
                    db.execute("INSERT INTO position_live VALUES (?, ?, ?)",
                               (event["agms"], event["position"], event_id))
                else:
                    changed = db.execute("DELETE FROM position_live WHERE agms=? AND start_id=?",
                                         (event["agms"], event["start_event_id"])).rowcount
                    if not changed:
                        db.execute("UPDATE position_operations SET state='ABORTED',settled=1 WHERE event_id=?",
                                   (event_id,))
                        return False
                db.execute("UPDATE position_operations SET state='COMMITTED' WHERE event_id=? AND attempt=?",
                           (event_id, attempt))
                return True

    def _abort_position_attempt(self, event_id, attempt=None):
        with self._shift_db_write_lock():
            with self._shift_db_connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM position_operations WHERE event_id=?", (event_id,)).fetchone()
                if not row or (attempt is not None and row["attempt"] != attempt):
                    return False
                if row["state"] == "COMMITTED":
                    # Recovery's missing-file observation may already be stale.
                    # A committed operation is never rolled back by compensation.
                    return False
                db.execute("DELETE FROM position_live WHERE start_id=?", (event_id,))
                db.execute("UPDATE position_operations SET state='ABORTED',settled=1 WHERE event_id=?", (event_id,))
                return True

    def _claim_event(self, agms):
        rows = self._position_rows("SELECT start_id FROM position_live WHERE agms=?", (agms,))
        if not rows:
            return None
        event = self._committed_position_operation(rows[0]["start_id"])
        if not event:
            raise BusyError("Η κεντρική κατοχή θέσης δεν έχει επιβεβαιωμένη ΕΝΑΡΞΗ.")
        return event

    def _event_states(self):
        # A single snapshot for report iteration, not one SMB connection/file.
        ready = self._position_rows("SELECT value FROM meta WHERE key='position_events_index_v1'")
        if not ready:
            return None  # Legacy import failed: retain raw diagnostic evidence.
        return {row["event_id"]: row["state"] for row in self._position_rows(
            "SELECT event_id,state FROM position_operations")}

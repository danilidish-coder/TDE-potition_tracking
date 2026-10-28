"""Durable completed historical work, separate from physical START/END events.

Phase D3 stage A. Public UI/report exposure is deliberately a later gate.
"""
from __future__ import annotations
from datetime import datetime
import json
from position_tracking_common import _clean, _norm_search
from position_tracking_store_io import BusyError


class HistoricalWorkMixin:
    def _init_historical_work(self):
        with self._shift_db_write_lock(), self._shift_db_connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS historical_work (
                action_id TEXT PRIMARY KEY, shift_id TEXT NOT NULL,
                agms TEXT NOT NULL, person_search TEXT NOT NULL,
                position TEXT NOT NULL, direction TEXT NOT NULL,
                start_at TEXT NOT NULL, end_at TEXT NOT NULL,
                payload TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS historical_by_shift ON historical_work(shift_id)")
            db.execute("CREATE INDEX IF NOT EXISTS historical_by_person ON historical_work(agms,start_at)")
            for op in ("UPDATE", "DELETE"):
                db.execute(f"""CREATE TRIGGER IF NOT EXISTS historical_work_no_{op.lower()}
                    BEFORE {op} ON historical_work BEGIN
                    SELECT RAISE(ABORT,'immutable historical work'); END""")

    def historical_for_shift(self, shift_id):
        with self._shift_db_connect() as db:
            rows = db.execute("SELECT payload FROM historical_work WHERE shift_id=? ORDER BY start_at,action_id",
                              (_clean(shift_id),)).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def add_historical_completed(self, *, shift_id, person, position, direction,
                                  start_at, end_at, reason, intent):
        """Accept one completed history item, atomically with declared officer audit.

        Never inserts position START/END, never changes position_live or active JSON.
        All conflict reads and both inserts share the same BEGIN IMMEDIATE transaction.
        """
        shift_id = _clean(shift_id)
        agms = _clean(person.agms)
        position = _clean(position)
        direction = _clean(direction).upper()
        reason = _clean(reason)
        if not shift_id or not agms or not intent or intent.get("action") != "HISTORICAL_ADD":
            raise ValueError("Επιλέξτε βάρδια και καταχωρισμένο χειριστή.")
        if position not in {str(n) for n in range(1, 15)} or direction not in {"ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"}:
            raise ValueError("Μη έγκυρη θέση ή κατεύθυνση.")
        if len(reason) < 5:
            raise ValueError("Η ιστορική καταχώριση απαιτεί αιτιολογία.")
        if not isinstance(start_at, datetime) or not isinstance(end_at, datetime) or end_at <= start_at:
            raise ValueError("Η ΛΗΞΗ πρέπει να είναι μεταγενέστερη της ΕΝΑΡΞΗΣ.")
        stamp_start = start_at.isoformat(timespec="seconds")
        stamp_end = end_at.isoformat(timespec="seconds")
        action_id = _clean(intent.get("action_id"))
        if not action_id or not isinstance(intent.get("intent"), dict):
            raise ValueError("Λείπει μοναδικό αναγνωριστικό ιστορικής ενέργειας.")
        name = _clean(person.full_name)
        payload = dict(action_id=action_id, shift_id=shift_id, agms=agms,
                       rank=_clean(person.rank), surname=_clean(person.surname),
                       given_name=_clean(person.given_name), full_name=name,
                       position=position, direction=direction,
                       start_at=stamp_start, end_at=stamp_end,
                       duration_seconds=int((end_at-start_at).total_seconds()),
                       reason=reason, actor=intent.get("declared_officer"),
                       identity="DECLARED_NOT_AUTHENTICATED",
                       recorded_at=intent.get("recorded_at"))
        with self._shift_db_write_lock(), self._shift_db_connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM officer_actions WHERE action_id=?", (action_id,)).fetchone()
            if old:
                receipt = json.loads(old["payload"])
                if receipt.get("intent") != intent["intent"] or receipt.get("action") != "HISTORICAL_ADD":
                    raise BusyError("Το αναγνωριστικό αφορά διαφορετική καταχώριση.")
                return receipt
            row = db.execute("SELECT data_json FROM shifts WHERE shift_id=?", (shift_id,)).fetchone()
            if not row:
                raise ValueError("Δεν βρέθηκε η επιλεγμένη βάρδια.")
            shift = json.loads(row["data_json"])
            shift_start = datetime.fromisoformat(shift["start_at"])
            shift_end = datetime.fromisoformat(shift.get("end_at") or datetime.now().isoformat())
            if start_at >= shift_end or end_at <= shift_start:
                raise ValueError("Η εργασία δεν ανήκει στο επιλεγμένο διάστημα βάρδιας.")

            def conflict(other_agms, other_position):
                if agms == other_agms:
                    raise ValueError("Υπάρχει ήδη καταγεγραμμένη εργασία του ίδιου ΑΓΜΣ στο διάστημα.")
                if position == other_position:
                    raise ValueError("Η φυσική θέση είναι ήδη κατειλημμένη στο διάστημα.")

            # Canonical committed events cover both ordinary END and atomic handovers,
            # including an END not yet copied into the personnel_sessions index.
            actual = db.execute("""SELECT s.agms,
                json_extract(s.payload,'$.position') AS position,
                COALESCE(h.timestamp,json_extract(s.payload,'$.timestamp')) AS started,
                json_extract(e.payload,'$.timestamp') AS ended
                FROM position_operations s
                LEFT JOIN position_operations e ON e.start_id=s.event_id
                    AND e.kind='END' AND e.state='COMMITTED'
                LEFT JOIN officer_start_heads h ON h.start_id=s.event_id
                WHERE s.kind='START' AND s.state='COMMITTED'
            """).fetchall()
            for item in actual:
                if item["started"] and item["started"] < stamp_end and (
                        item["ended"] is None or item["ended"] > stamp_start):
                    conflict(_clean(item["agms"]), _clean(item["position"]))
            # Legacy indexed sessions can predate the canonical operations migration.
            rows = db.execute("""SELECT agms,position FROM personnel_sessions
                                 WHERE start_at<? AND end_at>?""", (stamp_end, stamp_start)).fetchall()
            for row in rows:
                conflict(_clean(row["agms"]), _clean(row["position"]))
            rows = db.execute("""SELECT agms,position FROM historical_work
                                 WHERE start_at<? AND end_at>?""", (stamp_end, stamp_start)).fetchall()
            for row in rows:
                conflict(_clean(row["agms"]), _clean(row["position"]))
            receipt = {**intent, "record_id": action_id, "before": None,
                       "after": payload, "result": payload}
            self._insert_officer_action(db, receipt)
            db.execute("""INSERT INTO historical_work
                (action_id,shift_id,agms,person_search,position,direction,start_at,end_at,payload)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                       (action_id,shift_id,agms,_norm_search(f"{agms} {person.rank} {name}"),
                        position,direction,stamp_start,stamp_end,json.dumps(payload,ensure_ascii=False)))
            return receipt

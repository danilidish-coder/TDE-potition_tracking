"""Central Windows-account handoff logic, isolated from UI/SQLite replay.

Production invariants:
- Close only another Windows account on the exact same computer.
- A locked session, missing identity or another station NEVER implies END.
- End a START only while its immutable event ID still matches.
- Let a recorded offline END replay with its original ID/timestamp instead of
  writing an additional synthetic END at reconnection time.
- Operations are guarded by the original central handoff and officer locks.
"""
from __future__ import annotations


def close_previous_windows_user_positions(
    store, computer: str, windows_user: str, person_type, clean, busy_error,
    *, protected_start_ids=(),
) -> list[dict]:
    protected_start_ids = frozenset(protected_start_ids)
    """Auto-close only earlier Windows accounts on this exact workstation.

    A locked screen, idle Windows session, or another station is NOT a
    handoff. If either Windows account cannot be identified, fail safely
    rather than guessing. A shared lock handles concurrent instances of
    the new account. Exact START IDs prevent closing a replacement record.
    """
    current_computer = clean(computer).casefold()
    current_user = clean(windows_user).casefold()
    if not current_computer or not current_user:
        return []
    completed = []
    with store.officer_lock("__WINDOWS_USER_HANDOFF__", timeout=15.0):
        for item in store.active_all():
            recorded_computer = clean(item.get("computer")).casefold()
            recorded_user = clean(item.get("user")).casefold()
            if recorded_computer != current_computer or not recorded_user or recorded_user == current_user:
                continue
            start_id = clean(item.get("event_id"))
            if start_id in protected_start_ids:
                # A durable offline END already references this exact START.
                # Replay that original END (time/id), never synthesize a new END.
                continue
            agms = clean(item.get("agms"))
            if not start_id or not agms:
                continue
            person = person_type(
                agms=agms, rank=clean(item.get("rank")),
                surname=clean(item.get("surname")), given_name=clean(item.get("given_name")),
            )
            try:
                ended = store.end(
                    person, expected_start_event_id=start_id,
                    end_reason="WINDOWS_USER_HANDOFF_RECOVERY",
                )
            except ValueError:
                # An operator already closed the old START while recovering.
                if store.get_active(agms) is None:
                    continue
                raise
            except busy_error:
                # A concurrent END/START may have replaced this session.
                latest = store.get_active(agms)
                if latest is None or clean(latest.get("event_id")) != start_id:
                    continue
                raise
            details = {
                "computer": computer,
                "previous_windows_user": clean(item.get("user")),
                "new_windows_user": windows_user,
                "agms": agms,
                "position": clean(item.get("position")),
                "start_event_id": start_id,
                "end_event_id": clean(ended.get("event_id")),
                "observed_at": clean(ended.get("timestamp")),
                "end_time_note": "Time of detection; actual departure time unverified",
            }
            completed.append(details)
            try:
                store.log_admin_action("AUTO_END_WINDOWS_USER_HANDOFF", details)
            except Exception:
                # The END event carries an immutable end_reason even if the
                # supplemental administrative log is temporarily unavailable.
                pass
    return completed

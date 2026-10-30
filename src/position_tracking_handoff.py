"""Central Windows-account handoff logic, isolated from UI/SQLite replay.

Central identity changes do not mutate physical positions. The historical
replay adapter below remains isolated from the central-only entry point; no
queue is activated, discarded or converted by this compatibility hook.
"""
from __future__ import annotations


def close_previous_windows_user_positions(
    store, computer: str, windows_user: str, person_type, clean, busy_error,
    *, protected_start_ids=(),
) -> list[dict]:
    """Compatibility hook: a Windows identity change is never physical END.

    Keep the callable for legacy clients without reading or mutating central
    data. An actual END requires an explicit operator/officer action or the
    confirmed atomic handover. Historical queued records are left untouched.
    """
    return []


class HandoffBlocked(RuntimeError):
    """The previous account cannot be safely reconciled; retain all events."""


def reconcile_handoff_before_replay(
    store, journal, person_type, computer: str, windows_user: str,
) -> dict:
    """Perform handoff BEFORE replaying a new Windows user's START.

    1. Never hide or clear existing conflicts.
    2. Finish local account handoff into durable END operations first.
    3. Preserve the exact STARTs for which a durable offline END already
       exists (the original END ID and timestamp win).
    4. Close only still-centrally-active positions of an earlier account on
       this *same* computer, with server-side per-officer identity checks.
    5. Replay original local operations in insertion order.

    If any step fails, fail closed: pending operations remain in SQLite and
    a new START is never replayed ahead of unresolved central handoff.
    """
    computer = str(computer or "").strip()
    windows_user = str(windows_user or "").strip()
    if not computer or not windows_user:
        raise HandoffBlocked(
            "Δεν επιβεβαιώθηκε ο υπολογιστής ή ο λογαριασμός Windows. "
            "Ο συγχρονισμός αναστέλλεται, χωρίς διαγραφή εκκρεμών εγγραφών."
        )
    existing_conflicts = journal.conflicts()
    if existing_conflicts:
        return {
            "applied": [],
            "pending": journal.pending_count(),
            "conflicts": existing_conflicts,
        }
    # This is idempotent. A queued END for the previous Windows user stays
    # durable even if the central SMB share drops immediately afterwards.
    journal.auto_close_previous_windows_users(computer, windows_user)
    pending = journal._rows(("PENDING",))
    protected_ids = {
        str(op.get("start_id") or "").strip()
        for op in pending
        if op.get("kind") == "END" and op.get("start_id")
    }
    # A pending original END has precedence over synthetic central detection
    # time, even if two different Windows logins share the same BOOTH machine.
    store.close_previous_windows_user_positions(
        computer, windows_user, protected_start_ids=protected_ids,
    )
    return journal.sync(store, person_type)

"""Machine-wide durable outbox policy; never silently use a private user queue.

The original production v1.2.5 fell back to per-account LocalAppData
after PUBLIC access failure. That could hide pending events on user handoff.
No file or operation is ever deleted/migrated automatically by this module.
"""
from __future__ import annotations
import os
import sqlite3
import uuid
from pathlib import Path

def _local_root() -> Path:
    target = os.environ.get("TDE_POSITION_LOCAL_ROOT")
    root = Path(target) if target else Path(
        os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or
        (Path.home() / ".local" / "share")
    ) / "TDE_Krystallopigis" / "PositionTracking"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _machine_queue_root() -> Path:
    preferred = os.environ.get("TDE_POSITION_MACHINE_ROOT")
    public = os.environ.get("PUBLIC")
    if preferred:
        path = Path(preferred)
    elif public:
        path = Path(public) / "Documents" / "TDE_Krystallopigis" / "PositionTracking_Queue"
    elif os.name != "nt":
        # Portable non-Windows development and isolated tests only.
        path = _local_root() / "machine_queue"
    else:
        raise RuntimeError(
            "Δεν βρέθηκε η ΚΟΙΝΗ ΟΥΡΑ ΘΕΣΕΩΝ (PUBLIC). "
            "Δεν επιτρέπεται ιδιωτική ουρά ανά χρήστη Windows. "
            "Ελέγξτε το περιβάλλον του υπολογιστή."
        )

    check = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        check = path / (".writecheck_" + uuid.uuid4().hex)
        check.write_bytes(b"ok")
        check.unlink()
        check = None
    except OSError as exc:
        raise RuntimeError(
            "Η ΚΟΙΝΗ ΟΥΡΑ ΘΕΣΕΩΝ δεν είναι προσβάσιμη: " + str(path) +
            ". Δεν θα χρησιμοποιηθεί προσωπικός φάκελος Windows. "
            "Η καταχώριση μπλοκάρεται ώστε να μη χαθούν offline δεδομένα. "
            "Απαιτείται έλεγχος δικαιωμάτων."
        ) from exc
    finally:
        if check is not None:
            try:
                check.unlink(missing_ok=True)
            except OSError:
                pass

    # Older versions could leave real unsent operations in per-user folders.
    legacy = _local_root() / "machine_queue" / "position_outbox.sqlite3"
    if legacy.exists() and legacy.resolve() != (path / legacy.name).resolve():
        try:
            with sqlite3.connect(f"file:{legacy.as_posix()}?mode=ro", uri=True, timeout=2) as db:
                outstanding = db.execute(
                    "SELECT COUNT(*) FROM operations WHERE status IN ('PENDING', 'CONFLICT')"
                ).fetchone()[0]
        except (OSError, sqlite3.DatabaseError) as exc:
            raise RuntimeError(
                "Δεν ελέγχθηκε η παλιά προσωπική offline ουρά: " + str(legacy) +
                ". Μην τη διαγράψετε. Απαιτείται έλεγχος ΑΞΥΠ."
            ) from exc
        if outstanding:
            raise RuntimeError(
                f"Υπάρχουν {outstanding} ΕΚΚΡΕΜΕΙΣ εγγραφές στην παλιά προσωπική ουρά "
                + str(legacy) + ". Μην τη διαγράψετε. "
                "Απαιτείται συμφωνία πριν ενεργοποιηθεί η κοινή ουρά."
            )
    return path

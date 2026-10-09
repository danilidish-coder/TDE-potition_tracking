from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

def person(n):
    return MOD.PersonnelRecord(str(n), "ΑΣΤ", f"TEST{n}", "WORKER")

# OS lock, not stale mtime: a live owner MUST remain the owner beyond 60s.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    path = store._lock_path("123")
    with store.officer_lock("123"):
        old = (datetime.now() - timedelta(hours=4)).timestamp()
        os.utime(path, (old, old))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: next(
                iter([store.officer_lock("123").__enter__()])
            ))
            try:
                future.result(timeout=0.4)
            except TimeoutError:
                pass
            else:
                raise AssertionError("Live lock was stolen because its file looked old")
    # Acquire again after the previous owner releases normally.
    with store.officer_lock("123", timeout=2):
        pass

# Exactly one officer shift can start, even when 12 stations race.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    def start_shift(n):
        try:
            return store.start_officer_shift(person(n))
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(start_shift, range(12)))
    shifts = [x for x in outcomes if x]
    assert len(shifts) == 1, outcomes
    assert store.current_shift()["shift_id"] == shifts[0]["shift_id"]

# Concurrent START and shift state changes must not overwrite one another.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    worker = person(71)
    store.start(worker, "1", "ΕΙΣΟΔΟΣ")
    store.start_officer_shift(person(99))
    def mutate(n):
        store.set_shift_member_state(worker.agms, "EXCLUDED" if n % 2 else "APPROVED")
        store.sync_active_shift()
        return True
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(mutate, range(36)))
    shift = store.current_shift()
    assert sum(worker.agms in shift[k] for k in ("approved", "excluded", "pending")) == 1

# A disconnected or missing shared active directory cannot be mistaken for free space.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    store.active.rename(store.root / "unavailable_active")
    try:
        store.start(person(10), "2", "ΕΞΟΔΟΣ")
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("An unavailable central active directory allowed new START")

print("SHIFT_SMB_LOCK_CONCURRENCY: PASS")

from __future__ import annotations

import importlib.util
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

def person(n):
    return MOD.PersonnelRecord(str(n), "ΑΣΤ", f"TEST{n}", "ONE")

base = datetime.now() - timedelta(hours=1)
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    worker = person(1001)
    other = person(1002)
    first = store.start(worker, "8", "ΕΞΟΔΟΣ", when=base, client_id="PC-EXIT__USER-A__PID-1")
    assert store.get_active(worker.agms)["client_id"] == "PC-EXIT__USER-A__PID-1"
    try:
        store.end(worker, when=base + timedelta(minutes=1), expected_start_event_id="stale-start-id")
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Stale END deleted a newer booth owner")
    assert store.get_active(worker.agms)["event_id"] == first["event_id"]
    ended = store.end(
        worker, when=base + timedelta(minutes=2),
        expected_start_event_id=first["event_id"]
    )
    assert ended["start_event_id"] == first["event_id"]
    assert store.get_active(worker.agms) is None
    store.start(other, "8", "ΕΞΟΔΟΣ", when=base + timedelta(minutes=3), client_id="PC-EXIT__USER-B__PID-2")
    assert store.get_active(other.agms)["client_id"] == "PC-EXIT__USER-B__PID-2"
    assert store.get_active(worker.agms) is None

print("CLIENT_LIFECYCLE_REGRESSION: PASS")

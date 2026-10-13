from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)

def person(value):
    return MOD.PersonnelRecord(str(value), "ΑΣΤ", f"TEST{value}", "ONE")

base = (datetime.now() - timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
checks = 0

# 1: Closed position stays free if SQLite index write fails mid-end.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp) / "TDE_DATA")
    first = person(101)
    store.start(first, "1", "ΕΙΣΟΔΟΣ", when=base)
    original = store._store_personnel_session
    store._store_personnel_session = lambda *_: (_ for _ in ()).throw(MOD.BusyError("injected SQLite outage"))
    closed = store.end(first, when=base + timedelta(minutes=15))
    assert closed.get("session_index_pending")
    assert store.get_active(first.agms) is None
    store.start(person(102), "1", "ΕΞΟΔΟΣ", when=base + timedelta(minutes=16))
    store._store_personnel_session = original
    assert store.reconcile_pending_sessions() == 1
    assert any(row["agms"] == first.agms for row in store.search_personnel_sessions())
    checks += 1

# 2: Stale active marker with a durable END receipt does not trap the booth.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    p = person(201)
    started = store.start(p, "2", "ΕΞΟΔΟΣ", when=base)
    end = dict(started)
    end.update(event_id="ended", kind="END", start_event_id=started["event_id"],
               timestamp=(base + timedelta(minutes=5)).isoformat(timespec="seconds"))
    receipt = store.pending_index / (started["event_id"] + ".json")
    store._atomic_json(receipt, {"start": started, "end": end})
    assert store.get_active(p.agms) is None
    assert not store.active_all()
    store.start(person(202), "2", "ΕΙΣΟΔΟΣ", when=base + timedelta(minutes=6))
    checks += 1

# 3: A failed START marker must not create an orphan START event.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    original = store._atomic_json
    def fail_active(path, data):
        if Path(path).parent == store.active:
            raise OSError("injected SMB write error")
        return original(path, data)
    store._atomic_json = fail_active
    try:
        store.start(person(301), "3", "ΕΙΣΟΔΟΣ", when=base)
    except OSError:
        pass
    else:
        raise AssertionError("START incorrectly succeeded")
    assert store.iter_all_events() == []
    checks += 1

# 4: Corrupt active state must not appear as an available booth.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    (store.active / "999.json").write_text("{corrupt!", encoding="utf-8")
    try:
        store.start(person(302), "3", "ΕΙΣΟΔΟΣ", when=base)
    except MOD.BusyError:
        pass
    else:
        raise AssertionError("Corrupted shared active state was ignored")
    checks += 1

# 5: Audited correction must feed active booth, event history, and shift PDF data.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    officer = person(999)
    worker = person(401)
    store.start(worker, "4", "ΕΙΣΟΔΟΣ", when=base + timedelta(minutes=15))
    shift = store.start_officer_shift(officer, when=base + timedelta(minutes=10))
    edited = store.correct_active_start(
        worker.agms, base + timedelta(minutes=5), officer, "Network was inaccessible"
    )
    assert edited["original_start_at"] == (base + timedelta(minutes=15)).isoformat(timespec="seconds")
    assert store.get_active(worker.agms)["timestamp"] == (base + timedelta(minutes=5)).isoformat(timespec="seconds")
    items = store.shift_sessions_v2(shift)
    assert len(items) == 1 and items[0]["start_dt"] == base + timedelta(minutes=5), items
    final = store.end_officer_shift(officer, when=base + timedelta(minutes=30))
    assert final["closed_active_agms"] == [worker.agms]
    assert not store.active_all()
    matches = [x for x in store.search_personnel_sessions() if x["agms"] == worker.agms]
    assert matches and matches[0]["start_at"] == (base + timedelta(minutes=5)).isoformat(timespec="seconds")
    checks += 1

# 6: 7 simultaneous gkise must not claim the same physical booth.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    for round_no in range(8):
        booth = str(round_no + 10)
        def claim(index):
            p = person(5000 + round_no * 10 + index)
            try:
                store.start(p, booth, "ΕΙΣΟΔΟΣ" if index % 2 else "ΕΞΟΔΟΣ",
                            when=base + timedelta(minutes=round_no))
                return p
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=7) as pool:
            succeeded = [p for p in pool.map(claim, range(7)) if p]
        assert len(succeeded) == 1, (round_no, succeeded)
        assert sum(x["position"] == booth for x in store.active_all()) == 1
        store.end(succeeded[0], when=base + timedelta(minutes=round_no + 1))
        checks += 1

# 7: Repeated opening and closing must never leave ghost locks/active JSON.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    p = person(800)
    for i in range(250):
        now = base + timedelta(seconds=i * 4)
        store.start(p, "8", "ΕΙΣΟΔΟΣ", when=now)
        store.end(p, when=now + timedelta(seconds=2))
        assert store.get_active(p.agms) is None
    assert len(store.search_personnel_sessions()) == 250
    checks += 1

# 8: Publishing a version must not delete previous Releases, tags or branches.
publish = (ROOT / ".github" / "workflows" / "publish-release.yml").read_text(encoding="utf-8")
assert 'gh release delete "$old_tag"' not in publish
assert "Removing temporary branches" not in publish
checks += 1

print(f"NETWORK_RESILIENCE_REGRESSION: PASS ({checks} groups, 250 serial cycles, 56 concurrent claims)")

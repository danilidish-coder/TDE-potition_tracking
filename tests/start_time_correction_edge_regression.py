"""Audited start-time correction: validation, immutable original event, closed session."""
import importlib.util
import json
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
MOD=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)
def person(n):return MOD.PersonnelRecord(str(n),"ΑΣΤ","TIME","TEST")

with tempfile.TemporaryDirectory() as d:
    store=MOD.SharedEventStore(Path(d)/"data")
    officer=person(5100);worker=person(5200)
    start=datetime.now()-timedelta(minutes=5)
    earlier=start-timedelta(minutes=1)
    original=store.start(worker,"5","ΕΞΟΔΟΣ",when=start)
    corrected=store.correct_active_start(worker.agms,earlier,officer,"Temporary host outage")
    assert store.get_active(worker.agms)["timestamp"]==earlier.isoformat(timespec="seconds")
    assert store.get_active(worker.agms)["event_id"]==original["event_id"]
    assert corrected["original_start_at"]==start.isoformat(timespec="seconds")
    raw=[json.loads(p.read_text(encoding="utf-8")) for p in store.events.rglob("*.json") if original["event_id"] in p.name]
    assert len(raw)==1 and raw[0]["timestamp"]==start.isoformat(timespec="seconds")
    for when,reason in [
        (earlier-timedelta(days=1),"Yesterday invalid"),
        (datetime.now()+timedelta(days=1),"Future time invalid"),
        (earlier,"no"),
    ]:
        try:store.correct_active_start(worker.agms,when,officer,reason)
        except ValueError:pass
        else:raise AssertionError("Invalid correction accepted")
        assert store.get_active(worker.agms)["timestamp"]==earlier.isoformat(timespec="seconds")
    store.end(worker,when=datetime.now())
    try:store.correct_active_start(worker.agms,earlier,officer,"Already closed")
    except ValueError:pass
    else:raise AssertionError("Closed position modified")
    sessions=store.search_personnel_sessions()
    assert any(x["agms"]==worker.agms and x["start_at"]==earlier.isoformat(timespec="seconds") for x in sessions)
print("START_TIME_CORRECTION_EDGE_REGRESSION: PASS")

from __future__ import annotations

import importlib.util
import os
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

with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    c1 = "PC01__USER1"
    c2 = "PC02__USER2"

    store.write_client_heartbeat(c1, {"window_state": "ΑΝΟΙΧΤΟ"})
    store.write_client_heartbeat(c2, {"window_state": "ΕΛΑΧΙΣΤΟΠΟΙΗΜΕΝΟ"})
    online = {x["client_id"] for x in store.online_clients()}
    assert online == {c1, c2}, online

    msg = store.send_message(
        {"rank": "ΑΝΘ/ΜΟΣ", "surname": "ΔΟΚΙΜΗ", "given_name": "ΑΞΥΠ"},
        [c1, c2],
        "Μεταβείτε στη θέση 8.",
        "ΟΔΗΓΙΑ",
        "ΟΛΟΙ",
    )
    assert [m["message_id"] for m in store.pending_messages(c1)] == [msg["message_id"]]
    assert [m["message_id"] for m in store.pending_messages(c2)] == [msg["message_id"]]

    store.acknowledge_message(msg["message_id"], c1)
    assert store.pending_messages(c1) == []
    assert len(store.pending_messages(c2)) == 1
    acks = store.message_acknowledgements(msg["message_id"])
    assert len(acks) == 1 and acks[0]["client_id"] == c1

    cmd = store.send_close_command(
        {"rank": "ΑΝΘ/ΜΟΣ", "surname": "ΔΟΚΙΜΗ", "given_name": "ΑΞΥΠ"},
        c2,
        "Λήξη βάρδιας",
    )
    commands = store.pending_commands(c2)
    assert len(commands) == 1
    assert commands[0]["command_id"] == cmd["command_id"]
    assert commands[0]["type"] == "CLOSE_APP"

    store.acknowledge_command(cmd["command_id"], c2)
    assert store.pending_commands(c2) == []

    store.remove_client_heartbeat(c1)
    assert {x["client_id"] for x in store.online_clients()} == {c2}

    # Stale heartbeat must not appear online.
    stale_path = store.comm_clients / f"{MOD._safe_name(c2)}.json"
    data = __import__("json").loads(stale_path.read_text(encoding="utf-8"))
    data["last_seen"] = (datetime.now() - timedelta(minutes=2)).isoformat(timespec="seconds")
    stale_path.write_text(__import__("json").dumps(data, ensure_ascii=False), encoding="utf-8")
    assert store.online_clients(max_age_seconds=15) == []

# A physical position may have only one active officer, regardless of direction.
with tempfile.TemporaryDirectory() as tmp:
    store = MOD.SharedEventStore(Path(tmp))
    p1 = MOD.PersonnelRecord("100001", "ΑΡΧ/ΚΑΣ", "ΠΡΩΤΟΣ", "ΑΣΤΥΝΟΜΙΚΟΣ")
    p2 = MOD.PersonnelRecord("100002", "ΑΡΧ/ΚΑΣ", "ΔΕΥΤΕΡΟΣ", "ΑΣΤΥΝΟΜΙΚΟΣ")

    first = store.start(p1, "1", "ΕΙΣΟΔΟΣ")
    assert first["position"] == "1"

    try:
        store.start(p2, "1", "ΕΞΟΔΟΣ")
    except ValueError as exc:
        assert "ΘΕΣΗ 1" in str(exc)
        assert "χρησιμοποιείται ήδη" in str(exc)
    else:
        raise AssertionError("Duplicate physical position assignment was accepted.")

    second = store.start(p2, "2", "ΕΞΟΔΟΣ")
    assert second["position"] == "2"

assert isinstance(MOD._windows_session_is_active(), bool)
# Build synchronization marker: duplicate-position safeguard release.
print("COMMUNICATION_CONTROL_REGRESSION: PASS")

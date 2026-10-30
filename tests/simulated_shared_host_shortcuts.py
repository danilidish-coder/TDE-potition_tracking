from __future__ import annotations

"""A shared-host + many shortcut-launched stations simulation.

The scenario runs independent Python processes with ONE central TDE_DATA
directory. This is a filesystem integration test, not a physical Windows SMB
failover or proof of offline queueing.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location("position_tracking", ROOT / "src" / "position_tracking.py")
MOD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def person(num: str) -> object:
    return MOD.PersonnelRecord(str(num), "ΑΣΤ", f"TEST{num}", "CLIENT")


def run_station(root: Path, action: str, num: str, position: str = "-", username: str = "-", computer: str = "-",
                timeout: float = 45) -> dict:
    env = dict(os.environ)
    env["USERNAME"] = username
    env["TDE_SIMULATED_COMPUTER"] = computer
    p = subprocess.run(
        [sys.executable, str(SCRIPT), "--station", str(root), action, str(num), str(position)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=timeout,
    )
    if p.returncode:
        raise AssertionError(f"Station {computer} {username} {action} crashed: {p.returncode}\n{p.stdout}\n{p.stderr}")
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise AssertionError(f"Bad station output: {p.stdout} {p.stderr}") from exc


if len(sys.argv) >= 3 and sys.argv[1] == "--station":
    # Every process uses the same source; different parameters model each
    # workstation's existing shared-target shortcut.
    home = Path(sys.argv[2])
    task = sys.argv[3]
    num = sys.argv[4]
    booth = sys.argv[5] if len(sys.argv) > 5 else ""
    MOD.socket.gethostname = lambda: os.environ.get("TDE_SIMULATED_COMPUTER", "BOOTH")
    try:
        store = MOD.SharedEventStore(home)
        if task in ("start", "crash"):
            event = store.start(person(num), booth, "ΕΙΣΟΔΟΣ", client_id=f"SIM-{num}")
            if task == "crash":
                os._exit(42)
            result = {"ok": True, "id": event["event_id"], "position": booth}
        elif task == "end":
            event = store.end(person(num))
            result = {"ok": True, "id": event["event_id"]}
        elif task == "handoff":
            actions = store.close_previous_windows_user_positions(
                MOD.socket.gethostname(), os.environ.get("USERNAME") or ""
            )
            result = {"ok": True, "ended": [x["agms"] for x in actions]}
        elif task == "read":
            result = {"ok": True, "active": len(store.active_all())}
        else:
            raise RuntimeError(task)
    except (MOD.BusyError, ValueError, OSError) as err:
        result = {"ok": False, "error": type(err).__name__, "text": str(err)}
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


with tempfile.TemporaryDirectory(prefix="TDE-15-clients-") as tmp:
    base = Path(tmp)
    hub = base / "OFFICER_PC_SHARE"
    root = hub / "TDE_DATA"
    store = MOD.SharedEventStore(root)
    assert store.active_all() == []

    # 15 independent Windows-style shortcuts to the SAME central store:
    # one collides (15th wants booth 1), exactly 14 can claim positions.
    station_specs = [
        (f"{i+1000}", str((i % 14) + 1), f"WINUSER{i:02}", f"BOOTH-{i+1:02}")
        for i in range(15)
    ]
    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = [
            pool.submit(run_station, root, "start", agms, booth, user, computer, 60)
            for agms, booth, user, computer in station_specs
        ]
        answers = [f.result() for f in futures]
    successes = [(spec, answer) for spec, answer in zip(station_specs, answers) if answer["ok"]]
    denied = [(spec, answer) for spec, answer in zip(station_specs, answers) if not answer["ok"]]
    assert len(successes) == 14 and len(denied) == 1, (successes, denied)
    assert len(store.active_all()) == 14
    assert len({x["position"] for x in store.active_all()}) == 14

    # Server powered off: simulate the share path disappearing while the
    # pre-existing client process still holds a SharedEventStore reference.
    # The application must NOT report a phantom START or END success.
    if os.name != "nt":
        store_before_outage = MOD.SharedEventStore(root)
        offline_real = base / "OFFICER_PC_STOPPED"
        hub.rename(offline_real)
        hub.symlink_to(base / "unreachable_share", target_is_directory=True)
        try:
            for fn in (
                lambda: store_before_outage.get_active("1000"),
                lambda: store_before_outage.active_all(),
                lambda: store_before_outage.start(person("1099"), "15", "ΕΞΟΔΟΣ"),
            ):
                try:
                    outcome = fn()
                except (MOD.BusyError, OSError, FileNotFoundError):
                    continue
                raise AssertionError("Offline central server was treated as healthy: " + repr(outcome))
        finally:
            hub.unlink()
            offline_real.rename(hub)
        assert len(store.active_all()) == 14

    # D1: account changes preserve all physical STARTs. Only explicit END frees a booth.
    old_owner = next((spec for spec, reply in successes if spec[3] == "BOOTH-04"))
    old_id, old_pos, old_user, old_pc = old_owner
    handoff = run_station(root, "handoff", "NA", "-", "NEW_WINDOWS_USER", old_pc)
    assert handoff["ok"] and handoff["ended"] == [], handoff
    original = store.get_active(old_id)
    assert original is not None
    assert len(store.active_all()) == 14
    again = run_station(root, "handoff", "NA", "-", "NEW_WINDOWS_USER", old_pc)
    assert again["ended"] == [], again
    assert len(store.active_all()) == 14
    newcomer = run_station(root, "start", "2000", old_pos, "NEW_WINDOWS_USER", old_pc)
    assert not newcomer["ok"], "Windows user change cannot steal an occupied booth"
    store.end(person(old_id), expected_start_event_id=original["event_id"])
    newcomer = run_station(root, "start", "2000", old_pos, "NEW_WINDOWS_USER", old_pc)
    assert newcomer["ok"], newcomer
    assert len(store.active_all()) == 14

    # A process crash leaves its active booth recorded. Duty officer can close
    # it, and only then may another station claim the same physical booth.
    crash_target = "2000"
    terminated = subprocess.run(
        [sys.executable, str(SCRIPT), "--station", str(root), "crash", "2001", "15"],
        env={**os.environ, "USERNAME": "CRASH_USER",
             "TDE_SIMULATED_COMPUTER": "BOOTH-CRASH"},
        cwd=str(ROOT), capture_output=True, text=True, timeout=30,
    )
    assert terminated.returncode == 42, terminated.stderr
    occupied = run_station(root, "start", "2002", "15", "NEW", "BOOTH-OTHER")
    assert not occupied["ok"], occupied
    record = store.get_active("2001")
    assert record is not None
    ended = store.end(person("2001"), expected_start_event_id=record["event_id"])
    assert ended["kind"] == "END"
    resumed = run_station(root, "start", "2002", "15", "NEW", "BOOTH-OTHER")
    assert resumed["ok"]
    assert len(store.active_all()) == 15

    # Do not carry orphan locks across fresh end/start operations.
    for entry in list(store.active_all()):
        store.end(person(entry["agms"]), expected_start_event_id=entry["event_id"])
    assert store.active_all() == []
    cycles = 25
    for cycle in range(cycles):
        p = person(f"500{cycle}")
        store.start(p, "7", "ΕΙΣΟΔΟΣ")
        store.end(p)
    assert store.active_all() == []

print("SIMULATED_SHARED_HOST_SHORTCUTS: PASS (15 independent clients, 14 slots, offline share, Windows handoff, crash recovery, 25 cycles)")

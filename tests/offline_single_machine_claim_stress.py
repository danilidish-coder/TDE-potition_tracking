"""Stress: simultaneous offline claims by threads and separate Windows processes."""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve()
SPEC=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
MOD=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=MOD;SPEC.loader.exec_module(MOD)

def start(directory,i):
    person=MOD.PersonnelRecord(str(i),"ΑΣΤ","STRESS","CLIENT")
    try:
        result=MOD.OfflineJournal(directory).enqueue("START",person,"2","ΕΙΣΟΔΟΣ",str(i))
        return ("ok",result["operation_id"])
    except ValueError as exc:
        return ("rejected",str(exc))

if len(sys.argv)>1 and sys.argv[1]=="--child":
    print(json.dumps(start(Path(sys.argv[2]),int(sys.argv[3])),ensure_ascii=True))
    raise SystemExit(0)

with tempfile.TemporaryDirectory(prefix="TDE-offline-same-machine-") as d:
    root=Path(d)
    for cycle in range(6):
        folder=root/f"burst{cycle}"
        with ThreadPoolExecutor(max_workers=16) as pool:
            replies=list(pool.map(lambda i:start(folder,100*cycle+i),range(16)))
        assert sum(r[0]=="ok" for r in replies)==1,replies
        j=MOD.OfflineJournal(folder)
        assert j.pending_count()==1
    folder=root/"separate-processes"
    MOD.OfflineJournal(folder)
    def launch(i):
        r=subprocess.run([sys.executable,str(HERE),"--child",str(folder),str(9000+i)],
                         cwd=ROOT,capture_output=True,text=True,timeout=35)
        assert r.returncode==0,(r.stdout,r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])
    with ThreadPoolExecutor(max_workers=12) as pool:
        replies=list(pool.map(launch,range(12)))
    assert sum(r[0]=="ok" for r in replies)==1,replies
    journal=MOD.OfflineJournal(folder)
    assert journal.pending_count()==1
    for _ in range(200):
        assert MOD.OfflineJournal(folder).pending_count()==1
    renamed=folder/"position_outbox.renamed"
    journal.path.rename(renamed)
    renamed.rename(journal.path)
print("OFFLINE_SINGLE_MACHINE_CLAIM_STRESS: PASS (96 threads, 12 processes, 200 reopens)")

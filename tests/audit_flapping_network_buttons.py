"""Adversarial Qt regression: periodically changing connection status must not
keep START/END disabled while an unrelated status lookup is slow.
Audit only: this scenario was not in the v1.2.10 acceptance suite.
"""
from __future__ import annotations
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=Path(__file__).resolve()
spec=importlib.util.spec_from_file_location("position_tracking",ROOT/"src"/"position_tracking.py")
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)

if len(sys.argv)>1 and sys.argv[1]=="--child":
    from PySide6 import QtCore,QtWidgets
    base=Path(sys.argv[2])
    os.environ["TDE_POSITION_LOCAL_ROOT"]=str(base/"private")
    os.environ["TDE_POSITION_MACHINE_ROOT"]=str(base/"machine")
    os.environ["QT_QPA_PLATFORM"]="offscreen"
    central=base/"server"/"TDE_DATA"
    mod.SharedEventStore(central)
    mod.AppConfig.load=classmethod(lambda cls:cls(central_root=str(central),positions=[str(i) for i in range(1,15)]))
    orig=mod.SharedEventStore.get_active
    def delayed(self,agms):
        if agms=="99812":
            time.sleep(17)
        return orig(self,agms)
    mod.SharedEventStore.get_active=delayed
    orig_sync=mod.OfflineJournal.sync
    count=[0]
    def flapping(self,store,person_type):
        report=orig_sync(self,store,person_type)
        count[0]+=1
        report["network_error"]="temporary network response" if count[0]%2 else ""
        return report
    mod.OfflineJournal.sync=flapping
    class Probe(QtWidgets.QApplication):
        def __init__(self,argv):
            super().__init__(argv)
            self.selected_at=None
            self.window=None
            tick=QtCore.QTimer(self);tick.setInterval(120);tick.timeout.connect(self.maybe_select);tick.start()
            self.tick=tick
            QtCore.QTimer.singleShot(14500,self.on_timeout)
        def maybe_select(self):
            if self.window is not None:return
            w=next((x for x in self.topLevelWidgets() if hasattr(x,"agms_input") and hasattr(x,"start_btn")),None)
            if w is None or w.store is None or w._last_operator_sync_signature is None:return
            self.window=w
            person=mod.PersonnelRecord("99812","AST","FLAPPING","TEST")
            w.people=(person,)
            w._people_by_agms={person.agms:person}
            w.position.setCurrentText("8")
            w.agms_input.setText(person.agms)
            self.selected_at=time.monotonic()
            QtCore.QTimer.singleShot(7400,self.inspect)
        def inspect(self):
            w=self.window
            report={"agms_found":"FLAPPING" in w.person_name.text(),
              "start_enabled":w.start_btn.isEnabled(),"end_enabled":w.end_btn.isEnabled(),
              "sync_calls":count[0],"last_error":w._last_sync_error,
              "status":w.active_status.text(),
              "seconds":round(time.monotonic()-self.selected_at,2)}
            print("FLAPPING_RESULT:"+json.dumps(report,ensure_ascii=True),flush=True)
            os._exit(0 if report["agms_found"] and report["sync_calls"]>=3
                         and report["start_enabled"] and not report["end_enabled"] else 3)
        def on_timeout(self):
            print("FLAPPING_TEST_TIMEOUT",flush=True)
            os._exit(4)
    QtWidgets.QApplication=Probe
    mod.run(["Qt connection flapping audit"])
    raise SystemExit("Unexpected Qt return")

with tempfile.TemporaryDirectory() as d:
    env=dict(os.environ,QT_QPA_PLATFORM="offscreen")
    run=subprocess.run([sys.executable,"-u",str(SCRIPT),"--child",d],
                       cwd=str(ROOT),env=env,capture_output=True,text=True,
                       encoding="utf-8",errors="replace",timeout=25)
    print(run.stdout)
    assert run.returncode==0,(run.returncode,run.stderr[-1400:],run.stdout)
print("FLAPPING_NETWORK_START_BUTTON_STABLE: PASS")

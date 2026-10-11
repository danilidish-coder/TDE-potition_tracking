"""QA engine self-test. Confirm non-zero failures and no EXE after failed checks."""
import json, pathlib, subprocess, sys, tempfile
runner=pathlib.Path(__file__).with_name("qa_gate.py")
def case(commands,mode="test",minimum=1):
    with tempfile.TemporaryDirectory() as t:
        root=pathlib.Path(t); folder=root/"devcenter"; folder.mkdir()
        cfg={"format":"kp-qa/1","project":"QA ENGINE SELF TEST","tests":commands,
             "minimum_tests":minimum,"build":{"command":[sys.executable,"-c","print('BUILD')"],"output":"dist/test.exe"}}
        (folder/"qa.json").write_text(json.dumps(cfg),encoding="utf-8")
        r=subprocess.run([sys.executable,str(runner),mode,"--config",str(folder/"qa.json"),
                          "--reports",str(root/"reports")],capture_output=True,text=True,cwd=root)
        file=root/"reports"/("qa_windows.json" if sys.platform=="win32" else "qa_linux.json")
        d=json.loads(file.read_text(encoding="utf-8"))
        assert d["overall"]==("PASS" if r.returncode==0 else "FAIL")
        return r.returncode,d
ok={"id":"ok","command":[sys.executable,"-c","print('PASS')"]}
bad={"id":"fail","command":[sys.executable,"-c","raise SystemExit(9)"]}
missing={"id":"missing","command":["kp-test-nonexistent-command-29842"]}
assert case([ok])[0]==0
assert case([ok,bad])[0]!=0
assert case([missing])[0]!=0
assert case([],minimum=1)[0]!=0
assert case([ok],minimum=2)[0]!=0
code,report=case([bad],mode="full")
assert code!=0 and report["build"]["status"]=="NOT_RUN"
print("QA_ENGINE_SELFTEST: PASS (6 cases)")

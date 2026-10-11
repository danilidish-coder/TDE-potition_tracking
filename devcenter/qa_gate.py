"""Shared GitHub/local QA gate. Fail closed; never publish after a failed test.
Commands are trusted project code, NOT sandboxed. Do not run untrusted ZIPs.
"""
import argparse, datetime, hashlib, json, os, pathlib, platform, subprocess, sys, time

def check_command(c):
    return isinstance(c,list) and 0<len(c)<=64 and all(isinstance(s,str) and s and "\x00" not in s for s in c)

def execute(command,cwd,timeout):
    cmd=[sys.executable if v in ("python","python3") and i==0 else v for i,v in enumerate(command)]
    now=time.monotonic()
    try:
        r=subprocess.run(cmd,cwd=cwd,capture_output=True,stdin=subprocess.DEVNULL,
                         timeout=timeout,env={**os.environ,"PYTHONIOENCODING":"utf-8","PYTHONUTF8":"1"})
        output=(r.stdout+b"\n"+r.stderr).decode("utf-8","replace")
        return {"status":"PASS" if r.returncode==0 else "FAIL","exit_code":r.returncode,
                "seconds":round(time.monotonic()-now,2),"output":output[-20000:]}
    except subprocess.TimeoutExpired as e:
        return {"status":"TIMEOUT","seconds":round(time.monotonic()-now,2),
                "output":str(e),"exit_code":None}
    except OSError as e:
        return {"status":"ERROR","seconds":round(time.monotonic()-now,2),
                "output":str(e),"exit_code":None}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("mode",choices=("test","full"))
    a.add_argument("--config",default="devcenter/qa.json")
    a.add_argument("--reports",default="devcenter_reports")
    args=a.parse_args()
    cfgpath=pathlib.Path(args.config).resolve()
    root=cfgpath.parent.parent
    system=platform.system().lower()
    out=pathlib.Path(args.reports).resolve()
    out.mkdir(parents=True,exist_ok=True)
    result={"format":"kp-report/1","platform":system,"project":"","started":datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tests":[],"build":{"status":"NOT_RUN"},"overall":"FAIL","tested_count":0}
    try:
        cfg=json.loads(cfgpath.read_text(encoding="utf-8"))
        tests=cfg.get("tests")
        if cfg.get("format")!="kp-qa/1" or not isinstance(tests,list) or len(tests)<cfg.get("minimum_tests",1) or not tests:
            raise ValueError("Missing or insufficient required tests")
        result["project"]=cfg.get("project","")
        labels=set()
        for spec in tests:
            if not isinstance(spec,dict) or not spec.get("id") or spec["id"] in labels or not check_command(spec.get("command")):
                raise ValueError("Malformed or duplicate test definition")
            labels.add(spec["id"])
            if not isinstance(spec.get("timeout_seconds",180),int) or not 1<=spec.get("timeout_seconds",180)<=1800:
                raise ValueError("Invalid test timeout")
        applicable=[x for x in tests if system in x.get("platforms",["windows","linux","darwin"])]
        if not applicable:
            raise ValueError("No applicable tests")
        failed=False
        for spec in tests:
            if system not in spec.get("platforms",["windows","linux","darwin"]):
                result["tests"].append({"id":spec["id"],"status":"NOT_APPLICABLE"})
                continue
            r=execute(spec["command"],str(root),spec.get("timeout_seconds",180))
            result["tests"].append({"id":spec["id"],**r})
            result["tested_count"]+=1
            print(spec["id"],r["status"],"duration",r["seconds"],"s",flush=True)
            if r["status"]!="PASS":
                failed=True
                print(r["output"][-3000:],flush=True)
        if not failed:
            if args.mode=="test":
                result["overall"]="PASS"
            else:
                b=cfg.get("build")
                if system!="windows" or not isinstance(b,dict) or not check_command(b.get("command")):
                    raise ValueError("Windows build command missing")
                target=pathlib.Path(b.get("output",""))
                if target.is_absolute() or ".." in target.parts or str(target) in ("","."):
                    raise ValueError("Unsafe build target")
                target=root/target
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists(): target.unlink()
                r=execute(b["command"],str(root),b.get("timeout_seconds",900))
                result["build"]=r
                if r["status"]=="PASS" and target.is_file() and target.stat().st_size>0:
                    result["build"]["sha256"]=hashlib.sha256(target.read_bytes()).hexdigest()
                    result["build"]["bytes"]=target.stat().st_size
                    result["overall"]="PASS"
                else:
                    result["build"]["status"]="FAIL"
    except Exception as e:
        result["error"]=type(e).__name__+": "+str(e)
        print("FAIL:",result["error"],flush=True)
    finally:
        result["finished"]=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out/("qa_"+system+".json")).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        lines=[f"Project: {result['project']}",f"OS: {system}",f"Overall: {result['overall']}",
               f"Tests executed: {result['tested_count']}"]+[f"{x['id']}: {x['status']}" for x in result["tests"]]
        lines+=["Build: "+result["build"]["status"]]
        if "error" in result:lines.append(result["error"])
        text="\n".join(lines)+"\n"
        (out/("qa_"+system+".txt")).write_text(text,encoding="utf-8")
        print(text,flush=True)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:
                f.write("### QA gate — "+result["project"]+"\n\n"+"**"+result["overall"]+"**\n\n")
                f.write("| Test | Status |\n| --- | --- |\n")
                for x in result["tests"]:f.write("| "+x["id"]+" | "+x["status"]+" |\n")
    return 0 if result["overall"]=="PASS" else 1

if __name__=="__main__":
    raise SystemExit(main())

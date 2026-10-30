"""Bounded, fail-fast Windows recovery repro; each trial gets a fresh process."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from run_regressions import regression_environment


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--runs',type=int,default=8);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=True);root=Path(__file__).resolve().parents[1];results=[]
    for attempt in range(1,args.runs+1):
        try:
            result=subprocess.run([sys.executable,str(root/'tests'/'ui_workflow_regression.py')],cwd=root,env=regression_environment(),capture_output=True,text=True,encoding='utf-8',timeout=60)
            code,output=result.returncode,result.stdout+result.stderr
        except subprocess.TimeoutExpired as exc:code,output=124,str(exc)
        (args.out/f'attempt-{attempt:02d}.txt').write_text(output,encoding='utf-8')
        results.append({'attempt':attempt,'exit_code':code})
        (args.out/'results.json').write_text(json.dumps({'requested':args.runs,'attempts':results,'status':'FAIL' if any(r['exit_code'] for r in results) else 'PASS' if len(results)==args.runs else 'RUNNING'},indent=2)+'\n',encoding='utf-8')
        print(f'UI recovery attempt {attempt}: exit {code}',flush=True)
        if code:
            print(output,flush=True);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())

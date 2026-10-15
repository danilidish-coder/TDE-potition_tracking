"""Run every portable regression with isolated processes and honest outcomes."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    results = []
    for test in sorted((root / "tests").glob("*.py")):
        if test.name == "visual_flicker_windows.py":
            # This is a separate, mandatory Windows EXE/desktop CI step.
            continue
        started = time.monotonic()
        try:
            result = subprocess.run([sys.executable, str(test)], cwd=root, env=environment,
                                    capture_output=True, text=True, timeout=240)
            code, output = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = 124, str(exc)
        (out / (test.stem + ".log")).write_text(output, encoding="utf-8")
        results.append({"test": test.name, "exit_code": code,
                        "seconds": round(time.monotonic() - started, 3)})
        print(f"{test.name}: {'PASS' if code == 0 else 'FAIL'}", flush=True)
        if code:
            print(output, flush=True)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Scripts: {len(results)}; failed: {sum(r['exit_code'] != 0 for r in results)}")
    return int(not results or any(r["exit_code"] != 0 for r in results))


if __name__ == "__main__":
    raise SystemExit(main())

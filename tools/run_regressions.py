"""Run every portable regression with isolated processes and honest outcomes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

# Explicit user decision, 28 October 2026: strong officer identity is no longer
# required. Preserve/run the exact five old denial checks and report their real
# result separately; no functional/integrity regression is exempted.
HISTORICAL = {'central_officer_authorization_regression.py':
              '7d5c4dd410014a5b33d38cf0b97c444fb3584b0b3a159d4b294181dc347204c6'}


def retired_property_failure(code, output):
    return (code == 1 and 'FAILED (failures=5)' in output
            and output.count('AssertionError: UNAUTHORIZED_OFFICER_ACTION_ACCEPTED:') == 5)


def regression_environment():
    environment = dict(os.environ)
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    # A captured Windows pipe defaults to cp1252, unlike the interactive CI
    # console. Greek JSON from nested station processes must round-trip intact.
    environment["PYTHONUTF8"] = "1"
    environment["PYTHONIOENCODING"] = "utf-8"
    return environment


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    environment = regression_environment()
    results = []
    # Fast feedback for the exact Windows regressions that failed previously.
    # Full coverage still runs afterward, including all other test scripts.
    priority = ("test_offline_freeze_scenarios.py", "offline_durability_stage4_regression.py",
                "exit_responsiveness_regression.py")
    tests = sorted((root / "tests").glob("*.py"),
                   key=lambda test: (priority.index(test.name) if test.name in priority else len(priority), test.name))
    for test in tests:
        if test.name == "visual_flicker_windows.py":
            # This is a separate, mandatory Windows EXE/desktop CI step.
            continue
        started = time.monotonic()
        historical = test.name in HISTORICAL
        if historical and hashlib.sha256(test.read_bytes()).hexdigest() != HISTORICAL[test.name]:
            raise RuntimeError('Historical evidence changed: ' + test.name)
        try:
            result = subprocess.run([sys.executable, str(test)], cwd=root, env=environment,
                                    capture_output=True, text=True, encoding="utf-8", timeout=240)
            code, output = result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired as exc:
            code, output = 124, str(exc)
        (out / (test.stem + ".log")).write_text(output, encoding="utf-8")
        required_check = not historical or (code != 0 and not retired_property_failure(code, output))
        results.append({"test": test.name, "exit_code": code, "required": required_check,
                        "seconds": round(time.monotonic() - started, 3)})
        label = ' [HISTORICAL property, no longer required; actual result retained]' if historical and not required_check else ''
        print(f"{test.name}: {'PASS' if code == 0 else 'FAIL'}{label}", flush=True)
        if code:
            print(output, flush=True)
    (out / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    required = [r for r in results if r['required']]
    history = [r for r in results if not r['required']]
    print(f"Scripts: {len(required)}; failed: {sum(r['exit_code'] != 0 for r in required)}")
    print(f"Historical scripts: {len(history)}; failed: {sum(r['exit_code'] != 0 for r in history)} (not a required property)")
    return int(not required or any(r["exit_code"] != 0 for r in required))


if __name__ == "__main__":
    raise SystemExit(main())

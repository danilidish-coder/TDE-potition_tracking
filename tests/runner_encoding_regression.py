"""Nested Windows station JSON must survive captured pipes with Greek errors."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_regressions import regression_environment


class RunnerEncodingContract(unittest.TestCase):
    def test_nested_greek_station_response_round_trip(self):
        program = "import json; print(json.dumps({'error': chr(0x0397) + chr(0x03B8)}, ensure_ascii=False))"
        nested = (
            "import subprocess,sys; "
            f"r=subprocess.run([sys.executable,'-c',{program!r}],capture_output=True,text=True,check=True); "
            "print(r.stdout,end='')"
        )
        result = subprocess.run([sys.executable, "-c", nested], env=regression_environment(),
                                capture_output=True, text=True, encoding="utf-8", check=True, timeout=15)
        self.assertEqual(json.loads(result.stdout), {"error": "Ηθ"})


if __name__ == "__main__":
    unittest.main()

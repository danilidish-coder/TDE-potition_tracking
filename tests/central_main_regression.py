"""Production central-only entry: no sandbox guard, no legacy import, safe self-test."""
import ast
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import position_tracking_central_main as entry
from position_tracking_constants import CENTRAL_VERSION


class CentralEntry(unittest.TestCase):
    def test_entry_has_no_sandbox_guard_and_never_imports_the_legacy_entry(self):
        text = (SRC / "position_tracking_central_main.py").read_text(encoding="utf-8")
        self.assertNotIn("TDE_TRIAL_SANDBOX", text)
        self.assertNotIn("validate_trial_folder", text)
        tree = ast.parse(text)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
        self.assertNotIn("position_tracking", imported)
        self.assertNotIn("position_tracking_trial", imported)
        self.assertNotIn("position_tracking_ui_main", imported)

    def test_version_resource_and_title_agree(self):
        info = (ROOT / "tools" / "windows_version_info_central_v127.txt").read_text(encoding="utf-8")
        self.assertEqual(CENTRAL_VERSION, "1.2.7")
        self.assertIn("ProductVersion', '1.2.7'", info)
        self.assertIn("filevers=(1,2,7,0)", info)
        for name in ("position_tracking_ui_central.py", "position_tracking_ui_officer.py"):
            self.assertIn("{CENTRAL_VERSION}", (SRC / name).read_text(encoding="utf-8"))

    def test_selftest_passes_on_an_empty_folder_and_leaves_a_report(self):
        with tempfile.TemporaryDirectory(prefix="tde-selftest-") as base:
            target = Path(base) / "check"
            self.assertEqual(entry.run_selftest(target), 0)
            self.assertIn('"selftest": "PASS"', (target / "selftest_result.json").read_text(encoding="utf-8"))

    def test_selftest_does_not_require_legacy_only_modules(self):
        for name in ("docx", "position_tracking_documents", "position_tracking_statistics"):
            self.assertNotIn(name, entry.REQUIRED_MODULES)

    def test_selftest_refuses_a_folder_with_existing_data(self):
        with tempfile.TemporaryDirectory(prefix="tde-selftest-") as base:
            existing = Path(base) / ".tde_runtime"
            existing.mkdir()
            marker = existing / "real.txt"
            marker.write_text("keep", encoding="utf-8")
            self.assertEqual(entry.run_selftest(base), 3)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertEqual(sorted(p.name for p in Path(base).iterdir()), [".tde_runtime"])

    def test_missing_selftest_argument_is_refused_without_starting_the_gui(self):
        self.assertEqual(entry.main(["x", "--selftest"]), 3)

    def test_entry_runs_as_a_script_for_selftest(self):
        with tempfile.TemporaryDirectory(prefix="tde-selftest-") as base:
            result = subprocess.run([sys.executable, str(SRC / "position_tracking_central_main.py"),
                                     "--selftest", str(Path(base) / "x")],
                                    capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Isolated trial launcher cannot read/write the production central root."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from position_tracking_trial import SANDBOX_NAME, validate_trial_folder


class TrialSandbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tde-trial-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.sandbox = self.base / SANDBOX_NAME
        self.sandbox.mkdir()
        self.runtime = self.sandbox / ".tde_runtime"
        self.runtime.mkdir()
        self.settings = self.runtime / "position_tracking.settings.json"

    def test_only_explicit_trial_sandbox_directory_is_accepted(self):
        self.assertEqual(validate_trial_folder(self.sandbox), self.sandbox.resolve())
        with self.assertRaisesRegex(RuntimeError,"ξεχωριστό φάκελο"):
            validate_trial_folder(self.base)

    def test_old_settings_cannot_refer_to_production_or_parent(self):
        production = self.base / "real-service-data"
        production.mkdir()
        for value in (str(production.resolve()), "../../real-service-data"):
            self.settings.write_text(json.dumps({"central_root": value}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError,"εκτός του δοκιμαστικού"):
                validate_trial_folder(self.sandbox)

    def test_relative_root_inside_sandbox_is_permitted(self):
        self.settings.write_text(json.dumps({"central_root": ".tde_runtime"}), encoding="utf-8")
        self.assertEqual(validate_trial_folder(self.sandbox), self.sandbox.resolve())

    def test_invalid_settings_fail_closed(self):
        self.settings.write_text("{bad-json}", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_trial_folder(self.sandbox)


if __name__ == "__main__":
    unittest.main()

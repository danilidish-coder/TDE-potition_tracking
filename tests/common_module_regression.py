"""Stage 5: compatibility contract for extracted common helpers."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import position_tracking as app
from position_tracking_common import _clean, _norm_search, _safe_name


class CommonModuleContract(unittest.TestCase):
    def test_reexport_identity(self):
        self.assertIs(app._clean, _clean)
        self.assertIs(app._norm_search, _norm_search)
        self.assertIs(app._safe_name, _safe_name)

    def test_clean_existing_semantics(self):
        self.assertEqual(_clean("  A  B  "), "A B")
        self.assertEqual(_clean(None), "")
        self.assertEqual(_clean(0), "")

    def test_accent_insensitive_search(self):
        self.assertEqual(_norm_search("  Άννα   École  "), "ΑΝΝΑ ECOLE")

    def test_safe_name(self):
        self.assertEqual(_safe_name(" a/b: c "), "a_b_c")
        self.assertEqual(_safe_name("***"), "_")
        self.assertEqual(_safe_name(""), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()

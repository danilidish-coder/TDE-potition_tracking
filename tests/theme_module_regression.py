"""Theme normalization, no-GUI imports, and actual Qt background pixels."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import subprocess
import sys
import unittest

from PySide6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from position_tracking_theme import _theme_stylesheet


class ThemeModuleContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_standalone_import_has_no_gui_or_entry_dependency(self):
        program = (
            "import sys; sys.path.insert(0,'src'); import position_tracking_theme; "
            "assert 'position_tracking' not in sys.modules; "
            "assert not any(n.startswith('PySide6') for n in sys.modules)"
        )
        result = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_normalization_and_unknown_theme_keep_existing_fallback(self):
        self.assertEqual(_theme_stylesheet(' DARK '), _theme_stylesheet('dark'))
        self.assertEqual(_theme_stylesheet('invalid'), _theme_stylesheet('light'))
        self.assertEqual(_theme_stylesheet(None), _theme_stylesheet('light'))

    def test_actual_qt_root_pixels_switch_both_ways(self):
        window = QWidget()
        window.setObjectName('rootPanel')
        window.resize(80, 80)
        window.show()
        try:
            for theme, expected in [('light', '#eef3f7'), ('dark', '#07111f'), ('light', '#eef3f7')]:
                window.setStyleSheet(_theme_stylesheet(theme))
                self.app.processEvents()
                self.assertEqual(window.grab().toImage().pixelColor(40, 40).name(), expected)
        finally:
            window.close()


if __name__ == '__main__':
    unittest.main()

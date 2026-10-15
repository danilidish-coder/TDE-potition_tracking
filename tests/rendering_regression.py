"""Real Qt paint delivery, nested updates, and application theme integration."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from position_tracking_rendering import coherent_widget_update


class PaintObserver(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.painted = []

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Paint:
            self.painted.append(obj)
        return False


def application_check():
    import position_tracking as application
    original = QApplication.__init__
    errors = []
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        application._local_root = lambda: base / "local"
        application._machine_queue_root = lambda: base / "queue"
        application._app_dir = lambda: base

        def initialize(app, *args, **kwargs):
            original(app, *args, **kwargs)

            def exercise():
                try:
                    window = next(w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow")
                    observer = PaintObserver(window)
                    buttons = [b for b in window.findChildren(QPushButton) if b.isVisible()]
                    assert len(buttons) >= 10
                    for button in buttons:
                        button.installEventFilter(observer)
                    for _ in range(60):
                        before = window.config.theme
                        observer.painted.clear()
                        window.theme_btn.click()
                        assert window.config.theme != before
                        assert all(b in observer.painted for b in buttons), "A child missed the synchronous theme paint"
                        assert application.AppConfig.load().theme == window.config.theme
                    assert not window.agms_input.text()
                    assert window.store is None
                    print("APPLICATION_60_THEME_CHANGES_AND_PERSISTENCE: PASS", flush=True)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    # The real window intentionally ignores ordinary close/quit
                    # requests to avoid losing an operator's active position.
                    app.exit(0)

            QTimer.singleShot(100, exercise)

        QApplication.__init__ = initialize
        assert application.run(["theme-integration"]) == 0
        if errors:
            raise errors[0]


class RenderingContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        layout = QVBoxLayout(self.window)
        self.buttons = [QPushButton("Top"), QPushButton("Bottom")]
        for button in self.buttons:
            layout.addWidget(button)
        self.observer = PaintObserver(self.window)
        for button in self.buttons:
            button.installEventFilter(self.observer)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()

    def test_complete_tree_painted_before_return_without_pumping_events(self):
        queued = []
        QTimer.singleShot(0, lambda: queued.append(True))
        for color in ("#07111f", "#eef3f7") * 15:
            self.observer.painted.clear()
            with coherent_widget_update(self.window):
                self.window.setStyleSheet(f"QWidget {{ background: {color}; }}")
                self.assertFalse(self.window.updatesEnabled())
                self.assertFalse(self.observer.painted)
            self.assertTrue(all(b in self.observer.painted for b in self.buttons))
            self.assertFalse(queued, "Theme update reentered the event loop")
        self.app.processEvents()
        self.assertTrue(queued)

    def test_exception_restores_updates(self):
        with self.assertRaisesRegex(ValueError, "test"):
            with coherent_widget_update(self.window):
                raise ValueError("test")
        self.assertTrue(self.window.updatesEnabled())

    def test_nested_and_preexisting_disabled_child_are_preserved(self):
        self.buttons[1].setUpdatesEnabled(False)
        with coherent_widget_update(self.window):
            with coherent_widget_update(self.window):
                self.window.setStyleSheet("QWidget { color: red; }")
            self.assertFalse(self.window.updatesEnabled())
        self.assertTrue(self.window.updatesEnabled())
        self.assertFalse(self.buttons[1].updatesEnabled())
        self.window.setUpdatesEnabled(False)
        with coherent_widget_update(self.window):
            pass
        self.assertFalse(self.window.updatesEnabled())

    def test_actual_application(self):
        result = subprocess.run([sys.executable, __file__, "--application"], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("APPLICATION_60_THEME_CHANGES_AND_PERSISTENCE: PASS", result.stdout)


if __name__ == "__main__":
    if "--application" in sys.argv:
        application_check()
    else:
        unittest.main()

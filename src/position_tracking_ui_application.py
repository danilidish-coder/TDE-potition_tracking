"""Qt lifetime and initial-window presentation, with explicit runtime providers."""
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from position_tracking_ui_main import MainWindow
from position_tracking_ui_presentation import arm_initial_presentation
from position_tracking_diagnostics import start_runtime_diagnostics


def launch(args, services) -> int:
    app = QApplication(list(args or sys.argv))
    app.setApplicationName("TDE Position Tracking")
    try:
        window = MainWindow(services)
    except RuntimeError as exc:
        QMessageBox.critical(None, "ΚΟΙΝΗ ΟΥΡΑ ΘΕΣΕΩΝ — ΑΣΦΑΛΕΙΑ", str(exc))
        return 2
    diagnostics = start_runtime_diagnostics(app, window, services.local_root())
    presentation = arm_initial_presentation(window)
    window.show()
    return app.exec()

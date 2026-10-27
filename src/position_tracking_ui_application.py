"""Qt lifetime and initial-window presentation, with explicit runtime providers."""
import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from position_tracking_ui_main import MainWindow
from position_tracking_ui_presentation import arm_initial_presentation
from position_tracking_diagnostics import start_runtime_diagnostics


def launch(args, services) -> int:
    arguments = list(args or sys.argv)
    central_preview = "--central-only" in arguments
    arguments = [argument for argument in arguments if argument != "--central-only"]
    app = QApplication(arguments)
    app.setApplicationName("TDE Position Tracking")
    if central_preview:
        from position_tracking_ui_central import CentralOperatorWindow
        window = CentralOperatorWindow(services)
        presentation = arm_initial_presentation(window)
        window.show()
        return app.exec()
    try:
        window = MainWindow(services)
    except RuntimeError as exc:
        QMessageBox.critical(None, "ΚΟΙΝΗ ΟΥΡΑ ΘΕΣΕΩΝ — ΑΣΦΑΛΕΙΑ", str(exc))
        return 2
    diagnostics = start_runtime_diagnostics(app, window, services.local_root())
    presentation = arm_initial_presentation(window)
    window.show()
    return app.exec()

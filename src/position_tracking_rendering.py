"""Paint a theme change as a single top-level backing-store update.

No event-loop pumping, screenshots, overlays or hidden windows are involved.
Qt's normal backing store continues to own rendering and presentation.
"""
from contextlib import contextmanager

from PySide6.QtWidgets import QWidget


@contextmanager
def coherent_widget_update(window: QWidget):
    """Finish style/layout work before synchronously painting the widget tree.

    Disabling the top-level window already disables updates on its children.
    Separately enabling a child can schedule another update; instead restore
    only the state we own, and repaint the full window before returning to the
    event loop. Do not call processEvents here: queued business actions must not
    run in the middle of a theme transaction.
    """
    enabled = window.updatesEnabled()
    window.setUpdatesEnabled(False)
    try:
        yield
        window.ensurePolished()
        for child in window.findChildren(QWidget):
            child.ensurePolished()
        if window.layout() is not None:
            window.layout().activate()
    finally:
        window.setUpdatesEnabled(enabled)
        if enabled and window.isVisible():
            window.repaint()

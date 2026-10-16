"""Present the native window only after its first complete Qt backing-store paint.

This initial-show barrier is never used for later theme/state transitions.
No screenshots, overlays, nested event processing or timed exposure delays.
"""
import sys
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QGuiApplication


class FirstPaintPresentation(QObject):
    def __init__(self, window, set_cloaked):
        if window.isVisible():
            raise ValueError('Initial presentation must be armed before show')
        super().__init__(window)
        self._set_cloaked = set_cloaked
        self._root = window.centralWidget() if hasattr(window, 'centralWidget') else window
        self._root = self._root or window
        self._pending = False
        self._released = False
        set_cloaked(True)
        self._root.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._root and event.type() == QEvent.Paint and not self._pending:
            self._pending = True
            # The callback runs after the current synchronous backing-store draw
            # (including all descendants) has returned, never inside that paint.
            QTimer.singleShot(0, self.release)
        return False

    def release(self):
        if not self._released:
            self._set_cloaked(False)
            self._released = True
            self._root.removeEventFilter(self)


def arm_initial_presentation(window, set_cloaked=None):
    if set_cloaked is None:
        if sys.platform != 'win32' or QGuiApplication.platformName().lower() != 'windows':
            return None
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                              wintypes.LPCVOID, wintypes.DWORD]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        hwnd = int(window.winId())

        def set_cloaked(cloaked):
            value = wintypes.BOOL(cloaked)
            # DWMWA_CLOAK: keep rendering the real native backing store while
            # withholding its uninitialized surface from DWM presentation.
            result = dwm.DwmSetWindowAttribute(hwnd, 13, ctypes.byref(value), ctypes.sizeof(value))
            if result:
                raise RuntimeError(f'Initial window presentation failed (HRESULT {result})')
    return FirstPaintPresentation(window, set_cloaked)

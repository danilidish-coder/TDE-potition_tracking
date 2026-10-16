"""Select and clean only the EXE process tree launched by a visual test."""
import ctypes
from ctypes import wintypes
import os
import subprocess


def use_physical_pixel_coordinates():
    """Keep Win32 geometry/clicks in the same pixels as ImageGrab screenshots."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes = [wintypes.HANDLE]
    user.SetThreadDpiAwarenessContext.restype = wintypes.HANDLE
    if not user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4)):
        raise ctypes.WinError(ctypes.get_last_error())


def theme_button_point(bbox, dpi):
    left, top, right, bottom = bbox
    scale = dpi / 96.0
    return (right - round((28 + 20 + 86 + 16 + 108 / 2) * scale),
            top + round((22 + 12 + 34 / 2) * scale))


def descendant_pids(root_pid, processes):
    result = {root_pid}
    while True:
        expanded = result | {pid for pid, parent in processes if parent in result}
        if expanded == result:
            return result
        result = expanded


def process_snapshot():
    # PyInstaller onefile uses a bootloader parent and an application child.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(kernel, name)
        function.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        function.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        entries = []
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            entries.append((entry.th32ProcessID, entry.th32ParentProcessID))
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return entries
    finally:
        kernel.CloseHandle(snapshot)


def stop_process_tree(process):
    if os.name == "nt" and process.poll() is None:
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                capture_output=True, timeout=20)
        if result.returncode and process.poll() is None:
            raise RuntimeError(f"Cannot terminate visual EXE tree {process.pid}")
        process.wait(timeout=10)
    elif process.poll() is None:
        process.terminate()
        process.wait(timeout=10)


from contextlib import contextmanager


def activate_visual_background(hwnd):
    user = ctypes.WinDLL('user32', use_last_error=True)
    for name in ('SetForegroundWindow', 'BringWindowToTop', 'UpdateWindow'):
        getattr(user, name).argtypes = [wintypes.HWND]
        getattr(user, name).restype = wintypes.BOOL
    user.GetForegroundWindow.restype = wintypes.HWND
    user.BringWindowToTop(hwnd)
    user.SetForegroundWindow(hwnd)
    if user.GetForegroundWindow() != hwnd:
        raise RuntimeError('Cannot activate the owned visual background fixture')
    user.UpdateWindow(hwnd)
    dwm = ctypes.WinDLL('dwmapi')
    dwm.DwmFlush.restype = ctypes.c_long
    result = dwm.DwmFlush()
    if result:
        raise RuntimeError(f'Background DwmFlush failed: {result}')


@contextmanager
def stable_visual_desktop():
    """Keep an owned, responsive background behind the app, never an overlay."""
    import threading
    ready, stop = threading.Event(), threading.Event()
    state = {}

    def serve():
        hwnd = None
        user = ctypes.WinDLL('user32', use_last_error=True)
        try:
            use_physical_pixel_coordinates()
            user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                            wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                            ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                            wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
            user.CreateWindowExW.restype = wintypes.HWND
            user.DestroyWindow.argtypes = [wintypes.HWND]
            user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                         wintypes.UINT, wintypes.UINT, wintypes.UINT]
            user.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user.DispatchMessageW.restype = wintypes.LPARAM
            hwnd = user.CreateWindowExW(0x80, 'STATIC', 'TDE visual background fixture',
                                       0x80000000 | 0x10000000 | 5,
                                       user.GetSystemMetrics(76), user.GetSystemMetrics(77),
                                       user.GetSystemMetrics(78), user.GetSystemMetrics(79),
                                       None, None, None, None)
            if not hwnd:
                raise ctypes.WinError(ctypes.get_last_error())
            activate_visual_background(hwnd)
            state['hwnd'] = hwnd
            ready.set()
            message = wintypes.MSG()
            # Serve only this fixture's queue, even while the test is blocked
            # in EXE extraction/capture. Unpumped windows can become ghosted.
            while not stop.wait(0.005):
                while user.PeekMessageW(ctypes.byref(message), hwnd, 0, 0, 1):
                    user.TranslateMessage(ctypes.byref(message))
                    user.DispatchMessageW(ctypes.byref(message))
        except BaseException as exc:
            state['error'] = exc
            ready.set()
        finally:
            if hwnd:
                user.DestroyWindow(hwnd)

    thread = threading.Thread(target=serve, name='TDE-visual-background', daemon=True)
    thread.start()
    try:
        if not ready.wait(10):
            raise RuntimeError('Visual background thread did not initialize')
        if 'error' in state:
            raise state['error']
        yield state['hwnd']
        if 'error' in state:
            raise state['error']
    finally:
        stop.set()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError('Visual background message thread did not terminate')

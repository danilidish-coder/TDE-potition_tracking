"""Windows session state, separated from booth and network logic.

This is a STRICT behavior-preserving extraction from approved release v1.2.5.
Screen lock or temporary network disconnection must not imply END.
Only verified handoff to a different Windows account can close a position.
"""
from __future__ import annotations
import os

def _windows_session_is_active() -> bool:
    """Return False only for a demonstrably disconnected Windows logon session.

    Locking the screen (Win+L) is not a disconnection. Console and RDP
    sessions are checked via WTSConnectState, not just console session ID.
    On an API failure, retain the position rather than closing it wrongly.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
        session_id = wintypes.DWORD()
        if not kernel32.ProcessIdToSessionId(
            kernel32.GetCurrentProcessId(), ctypes.byref(session_id)
        ):
            return True
        buffer = ctypes.c_void_p()
        returned = wintypes.DWORD()
        # WTSConnectState=8; WTSDisconnected=4, WTSReset=7, WTSDown=8.
        if not wts.WTSQuerySessionInformationW(
            None, session_id.value, 8,
            ctypes.byref(buffer), ctypes.byref(returned)
        ):
            return True
        try:
            if not buffer.value or returned.value < 4:
                return True
            state = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
            return state not in (4, 7, 8, 9)
        finally:
            if buffer.value:
                wts.WTSFreeMemory(buffer)
    except Exception:
        return True

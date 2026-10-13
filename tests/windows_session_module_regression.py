"""Deterministic, dependency-free tests for the extracted Windows session module."""
from __future__ import annotations
import ast
import ctypes
import importlib.util
from pathlib import Path
import types
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'src'/'position_tracking_windows_session.py'
spec=importlib.util.spec_from_file_location('position_tracking_windows_session', SOURCE)
assert spec and spec.loader
ws=importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)

# The main application must use the module, with no duplicate local implementation.
app=ast.parse((ROOT/'src'/'position_tracking.py').read_text(encoding='utf-8'))
assert not any(isinstance(n,ast.FunctionDef) and n.name=='_windows_session_is_active' for n in app.body)
assert any(isinstance(n,ast.ImportFrom) and n.module=='position_tracking_windows_session'
               and any(a.name=='_windows_session_is_active' for a in n.names)
               for n in app.body)
if ws.os.name!='nt':
    assert ws._windows_session_is_active() is True

class Kernel32:
    @staticmethod
    def GetCurrentProcessId(): return 101
    @staticmethod
    def ProcessIdToSessionId(pid,target):
        assert pid==101
        ctypes.cast(target,ctypes.POINTER(ctypes.c_ulong)).contents.value=32
        return True

class Wts:
    def __init__(self,state,success=True):
        self.value=ctypes.c_ulong(state)
        self.success=success
        self.freed=False
    def WTSQuerySessionInformationW(self,_,session,info,output,size):
        assert session==32 and info==8
        if not self.success:return False
        ctypes.cast(output,ctypes.POINTER(ctypes.c_void_p)).contents.value=ctypes.addressof(self.value)
        ctypes.cast(size,ctypes.POINTER(ctypes.c_ulong)).contents.value=ctypes.sizeof(self.value)
        return True
    def WTSFreeMemory(self,ptr):
        assert ptr
        self.freed=True

def check(state,expected,success=True):
    wts=Wts(state,success)
    def dll(name,use_last_error=True):
        if name=='kernel32':return Kernel32()
        assert name=='wtsapi32'
        return wts
    with patch.object(ws,'os',types.SimpleNamespace(name='nt')):
        with patch.object(ctypes,'WinDLL',dll,create=True):
            result=ws._windows_session_is_active()
    assert result is expected,(state,result,expected)
    if success:assert wts.freed,'WTS allocation must be freed'

for state in (0,1,2,3,5,6):check(state,True)
for state in (4,7,8,9):check(state,False)
check(4,True,success=False)
print('WINDOWS_SESSION_MODULE: PASS (module integration, 11 WTS cases, fail-safe)')

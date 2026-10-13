"""No-admin, one-time self-cache for launch when the shared Windows host is off.

Every user initially opens the EXISTING central EXE shortcut. That first
successful run seeds a private local EXE and places a desktop shortcut that
points to the local launcher. No Python installation on booth computers.
"""
from __future__ import annotations
import base64
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def cache_windows_client(local_root: str | Path, shared_executable: str):
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    dest = Path(local_root) / "client"
    dest.mkdir(parents=True, exist_ok=True)
    current = dest / "TDE_PositionTracking.exe"
    next_path = dest / "TDE_PositionTracking.next.exe"
    incoming = dest / "TDE_PositionTracking.copying"
    try:
        shared = Path(shared_executable)
        if shared.is_file() and shared.resolve() != current.resolve():
            def checksum(p):
                h = hashlib.sha256()
                with p.open("rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        h.update(block)
                return h.digest()
            if not current.exists() or (shared.stat().st_size != current.stat().st_size or checksum(shared) != checksum(current)):
                shutil.copyfile(shared, incoming)
                if checksum(incoming) != checksum(shared):
                    raise IOError("Το αντίγραφο της εφαρμογής δεν επαληθεύτηκε")
                if current.exists():
                    os.replace(incoming, next_path)  # swap before next launch, never while running
                else:
                    os.replace(incoming, current)
    finally:
        incoming.unlink(missing_ok=True)
    if not current.exists():
        return False
    launcher = dest / "start_position_tracking.cmd"
    launcher.write_text(
        '@echo off\r\n'
        'setlocal\r\n'
        'cd /d "%~dp0"\r\n'
        'if exist "TDE_PositionTracking.next.exe" move /Y "TDE_PositionTracking.next.exe" "TDE_PositionTracking.exe" >nul\r\n'
        'start "" "TDE_PositionTracking.exe"\r\n',
        encoding="utf-8",
    )
    # Standard Windows user account suffices; nothing goes into Program Files.
    # Use Shell API to respect OneDrive-redirected desktops.
    script = ("$w = New-Object -ComObject WScript.Shell; "
              "$desk = [Environment]::GetFolderPath('DesktopDirectory'); "
              f"$lnk = $w.CreateShortcut([IO.Path]::Combine($desk,'Καταγραφή Θέσεων.lnk')); "
              f"$lnk.TargetPath = '{str(launcher).replace(chr(39),chr(39)*2)}'; "
              f"$lnk.WorkingDirectory = '{str(dest).replace(chr(39),chr(39)*2)}'; "
              f"$lnk.IconLocation = '{str(current).replace(chr(39),chr(39)*2)},0'; "
              "$lnk.Save()")
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                   capture_output=True, check=True, timeout=20)
    return True

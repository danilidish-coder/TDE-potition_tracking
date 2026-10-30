"""Settings persistence and local runtime paths; no UI or shared-store dependency.

Callers may supply explicit paths. The legacy entry facade passes its overridable
path providers so existing integrations and isolated tests retain their behavior.
"""
from __future__ import annotations
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from position_tracking_common import _clean
from position_tracking_machine_queue import _local_root

SETTINGS_NAME = "position_tracking.settings.json"
DEFAULT_CUTOFF = "10:00"

def _app_dir() -> Path:
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent
    except Exception:
        return Path.cwd()



def _exe_dir() -> Path:
    return _app_dir()



def _runtime_root(app_directory: Path | None = None) -> Path:
    root = (app_directory if app_directory is not None else _app_dir()) / ".tde_runtime"
    root.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            path = str(root)
            attrs = kernel32.GetFileAttributesW(path)
            invalid = 0xFFFFFFFF
            hidden = 0x00000002
            if attrs != invalid and not (attrs & hidden):
                kernel32.SetFileAttributesW(path, attrs | hidden)
        except Exception:
            pass
    return root



def _open_path(path: str | Path) -> None:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True) if p.suffix == "" else p.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(p)])



def _fallback_settings_path() -> Path:
    public = os.environ.get("PUBLIC")
    if public:
        return Path(public) / "Documents" / "TDE_Krystallopigis" / SETTINGS_NAME
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "TDE_Krystallopigis" / SETTINGS_NAME



def _settings_path() -> Path:
    return _local_root() / SETTINGS_NAME



@dataclass
class AppConfig:
    central_root: str = ""
    shared_exe_path: str = ""
    personnel_file: str = ""
    cutoff: str = DEFAULT_CUTOFF
    positions: list[str] | None = None
    admin_pin_hash: str = ""
    theme: str = "light"

    def __post_init__(self):
        booth_positions = [str(i) for i in range(1, 15)]
        if self.positions is None:
            self.positions = booth_positions
        else:
            cleaned = [_clean(x) for x in self.positions if _clean(x)]
            for pos in booth_positions:
                if pos not in cleaned:
                    cleaned.append(pos)
            self.positions = cleaned

    @classmethod
    def load(cls, *, path: Path | None = None, app_directory: Path | None = None) -> "AppConfig":
        path = path if path is not None else _settings_path()
        if not path.is_file():
            # Migration: recover the shared EXE settings only while reachable.
            try:
                shared = (app_directory if app_directory is not None else _app_dir()) / ".tde_runtime" / SETTINGS_NAME
                if shared.is_file():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(shared, path)
            except OSError:
                pass
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls(
                central_root=_clean(data.get("central_root")),
                shared_exe_path=_clean(data.get("shared_exe_path")),
                personnel_file=_clean(data.get("personnel_file")),
                cutoff=_clean(data.get("cutoff")) or DEFAULT_CUTOFF,
                positions=[_clean(x) for x in data.get("positions", []) if _clean(x)] or None,
                admin_pin_hash=_clean(data.get("admin_pin_hash")),
                theme=(_clean(data.get("theme")).lower() if _clean(data.get("theme")).lower() in {"light", "dark"} else "light"),
            )
        except Exception:
            return cls()

    def save(self, *, path: Path | None = None) -> Path:
        path = path if path is not None else _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return path


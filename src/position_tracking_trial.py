"""Guarded entry point for an ISOLATED central-only Windows trial.

The trial refuses to run in the approved EXE directory or with central data
configured outside the clearly named trial sandbox. It cannot replace the
approved production executable.
"""
from __future__ import annotations
from pathlib import Path
import json
import sys

SANDBOX_NAME = "TDE_TRIAL_SANDBOX"


def validate_trial_folder(directory: str | Path) -> Path:
    folder = Path(directory).resolve()
    if folder.name.upper() != SANDBOX_NAME:
        raise RuntimeError(
            "Το δοκιμαστικό EXE λειτουργεί μόνο σε ξεχωριστό φάκελο "
            + SANDBOX_NAME + ". Δεν επιτρέπεται χρήση σε παραγωγικό φάκελο.")
    runtime = folder / ".tde_runtime"
    if runtime.exists() and not runtime.resolve().is_relative_to(folder):
        raise RuntimeError("Τα δοκιμαστικά δεδομένα δείχνουν εκτός του απομονωμένου φακέλου.")
    cfg = runtime / "position_tracking.settings.json"
    if cfg.exists():
        if not cfg.resolve().is_relative_to(folder):
            raise RuntimeError("Οι ρυθμίσεις προέρχονται από εξωτερικό κοινόχρηστο φάκελο.")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        target = str(data.get("central_root") or "").strip()
        if target:
            root = Path(target)
            root = root if root.is_absolute() else folder / root
            if not root.resolve().is_relative_to(folder):
                raise RuntimeError("Η κεντρική διαδρομή δείχνει εκτός του δοκιμαστικού φακέλου.")
    return folder


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or sys.argv)
    folder = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    try:
        validate_trial_folder(folder)
    except (OSError, ValueError, RuntimeError) as error:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), "ΔΟΚΙΜΑΣΤΙΚΗ ΕΚΔΟΣΗ — ΑΠΑΓΟΡΕΥΣΗ", 0x10)
        else:
            print(str(error), file=sys.stderr)
        return 2
    from position_tracking import run
    if "--central-only" not in argv and "--central-officer" not in argv:
        argv.append("--central-only")
    return int(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())

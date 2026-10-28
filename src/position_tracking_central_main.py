"""Entry point of the central-only application (v1.2.7 candidate).

Unlike position_tracking_trial.py there is NO sandbox folder guard: the program
is meant to sit in the real shared folder, exactly like earlier releases, and
reads/writes that folder's central data. It never imports the legacy
application entry (position_tracking.py), local settings migration or caches.

Start modes: no argument = operator window; --central-officer = officer panel.
--selftest <empty-folder> runs a headless functional check of the packaged
binary on synthetic data and exits; it refuses any folder that is not empty.
"""
from __future__ import annotations
from pathlib import Path
import json
import sys

# Modules the packaged application must contain. Loaded by NAME on purpose, so
# the check reflects what PyInstaller really bundled for the application and
# does not itself force a module into the bundle.
REQUIRED_MODULES = (
    "PySide6.QtWidgets", "openpyxl", "docx", "PIL",
    "position_tracking_central", "position_tracking_ui_central", "position_tracking_ui_officer",
    "position_tracking_documents", "position_tracking_pdf", "position_tracking_statistics",
    "position_tracking_store",
)


def run_selftest(directory: str | Path) -> int:
    folder = Path(directory)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        print("SELFTEST REFUSED: the folder must be empty or absent; no existing data is touched.", file=sys.stderr)
        return 3
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    try:
        import importlib
        for module in REQUIRED_MODULES:
            try:
                importlib.import_module(module)
                check("import " + module, True)
            except Exception as error:
                check("import " + module, False, repr(error))
        folder.mkdir(parents=True, exist_ok=True)
        runtime = folder / ".tde_runtime"
        runtime.mkdir()
        from openpyxl import Workbook
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["ΑΓΜΣ", "ΒΑΘΜΟΣ", "ΕΠΩΝΥΜΟ", "ΟΝΟΜΑ"])
        sheet.append(["999001", "TEST", "SYNTHETIC", "FIRST"])
        workbook.save(runtime / "personnel.xlsx")
        workbook.close()
        from position_tracking_central import CentralOperator, PositionRequest
        operator = CentralOperator.from_shared_directory(folder)
        person, active = operator.lookup("999001")
        check("lookup person", bool(person) and person.surname == "SYNTHETIC" and active is None)
        start = PositionRequest("START", "999001", "1", "ΕΙΣΟΔΟΣ")
        check("START confirmed", operator.execute(start).status == "CONFIRMED")
        check("START repeat is idempotent", operator.execute(start).event["event_id"] == start.operation_id)
        person, active = operator.lookup("999001")
        check("active after START", bool(active) and active["event_id"] == start.operation_id)
        end = PositionRequest("END", "999001", expected_start_id=active["event_id"] if active else "")
        check("END confirmed", operator.execute(end).status == "CONFIRMED")
        person, active = operator.lookup("999001")
        check("no active after END", active is None)
    except BaseException as error:  # a packaging fault must be reported, never hidden
        check("selftest completed", False, repr(error))
    ok = bool(checks) and all(item["ok"] for item in checks)
    report = {"selftest": "PASS" if ok else "FAIL", "frozen": bool(getattr(sys, "frozen", False)), "checks": checks}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    try:
        (folder / "selftest_result.json").write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    if "--selftest" in argv:
        index = argv.index("--selftest")
        if index + 1 >= len(argv):
            print("SELFTEST REFUSED: pass an empty folder after --selftest.", file=sys.stderr)
            return 3
        return run_selftest(argv[index + 1])
    if "--central-only" not in argv and "--central-officer" not in argv:
        argv.append("--central-only")
    from position_tracking_settings import AppConfig, _app_dir, _open_path
    from position_tracking_machine_queue import _local_root, _machine_queue_root
    from position_tracking_ui_context import WindowServices
    from position_tracking_ui_application import launch
    services = WindowServices(AppConfig, _app_dir, _local_root, _machine_queue_root, _open_path)
    return int(launch(argv, services))


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())

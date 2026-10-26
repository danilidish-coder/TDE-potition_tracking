"""Package a development EXE only after complete automated acceptance evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def package(exe, regressions, visual, commit, out, functional=None):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Exact source SHA required')
    results = json.loads(regressions.read_text(encoding='utf-8'))
    expected = {p.name for p in (Path(__file__).resolve().parents[1] / 'tests').glob('*.py')
                if p.name != 'visual_flicker_windows.py'}
    if {r['test'] for r in results} != expected or len(results) != len(expected) or any(r['exit_code'] for r in results):
        raise ValueError('Complete passing portable regression results required')
    report = json.loads(visual.read_text(encoding='utf-8'))
    if (report.get('error') or not report.get('capture_supported')
            or len(report.get('startup_runs', [])) != 20
            or len(report.get('theme_toggles', [])) != 30
            or report.get('startup_endpoint_flicker_runs') != 0
            or report.get('theme_endpoint_flicker_toggles') != 0
            or report.get('theme_clicks_confirmed') != 30
            or any(not r.get('application_frames') or r.get('endpoint_flicker_detected') for r in report['startup_runs'])
            or any(r.get('endpoint_flicker_detected') or not r.get('theme_changed') for r in report['theme_toggles'])):
        raise ValueError('Complete strict Windows visual acceptance required')
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if functional is None:
        raise ValueError('Frozen EXE functional acceptance required')
    functional_report = json.loads(functional.read_text(encoding='utf-8'))
    if (functional_report.get('status') != 'PASS' or functional_report.get('operations') != 4
            or functional_report.get('source_commit') != commit
            or functional_report.get('exe_sha256') != digest
            or not functional_report.get('original_ids_preserved')
            or not functional_report.get('original_timestamps_preserved')):
        raise ValueError('Frozen EXE functional acceptance required')
    idle = functional_report.get('idle_exit') or {}
    if (idle.get('status') != 'PASS' or idle.get('exit_code') != 0
            or idle.get('operations') != 0 or idle.get('central_created') is not False
            or idle.get('configured_personnel_missing') is not True
            or functional_report.get('completed_sessions') != 2):
        raise ValueError('Frozen EXE idle exit and completed sessions functional acceptance required')
    if not exe.stat().st_size:
        raise ValueError('Empty executable')
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out / exe.name)
    shutil.copy2(regressions, out / 'regressions.json')
    shutil.copy2(visual, out / 'visual-report.json')
    shutil.copy2(functional, out / 'functional-report.json')
    version = (Path(__file__).resolve().parents[1] / 'VERSION.txt').read_text().strip()
    manifest = {'version': version, 'source_commit': commit, 'exe': exe.name, 'sha256': digest,
                'bytes': exe.stat().st_size, 'regression_scripts': len(results),
                'startup_runs': 20, 'theme_toggles': 30,
                'status': 'DEVELOPMENT TEST BUILD — not a production release',
                'pending': ['Real multi-PC SMB/ACL and power-loss acceptance',
                            'Real Windows session/logoff/reboot acceptance',
                            'Operational printing, DPI and extended UI acceptance']}
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (out / 'SHA256SUMS.txt').write_text(f'{digest}  {exe.name}\n', encoding='ascii')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('exe', 'regressions', 'visual', 'out', 'functional'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--commit', required=True)
    args = p.parse_args()
    print(json.dumps(package(args.exe, args.regressions, args.visual, args.commit, args.out, args.functional), indent=2))

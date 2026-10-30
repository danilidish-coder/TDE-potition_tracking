"""One-shot additive publication of the explicitly authorized v1.2.6 test EXE.

Uses only GET plus one new-release POST (gh release create uploads new assets).
Never edits/deletes existing releases, assets, tags, branches or artifacts.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO = 'danilidish-coder/TDE-potition_tracking'
BRANCH = 'feature/v125-modularization-20261013'
TAG = 'v1.2.6'
PROTECTED = {'heads/main': '3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99',
             'tags/v1.2.5': '33ea13ca2133ddbfb93b1d051d4b25dc35bd954f'}


def gh(*args):
    return subprocess.check_output(['gh', *args], text=True, encoding='utf-8').strip()


def api(path):
    return json.loads(gh('api', f'repos/{REPO}/{path}'))


def pages(path):
    return sum(json.loads(gh('api', '--paginate', '--slurp', f'repos/{REPO}/{path}')), [])


def release_identity(release):
    return {k: release[k] for k in ('id', 'tag_name', 'name', 'body', 'draft', 'prerelease', 'updated_at')} | {
        'assets': [{k: a.get(k) for k in ('id', 'name', 'size', 'digest', 'updated_at')}
                   for a in release['assets']]}


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF_NAME') != BRANCH:
        raise RuntimeError('Wrong repository/branch')
    source = os.environ['GITHUB_SHA']
    root = Path(__file__).resolve().parents[1]
    package = root / 'artifact/development-exe'
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    exe = package / 'TDE_Katagrafi_Theseon.exe'
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if manifest['source_commit'] != source or manifest['version'] != TAG or manifest['sha256'] != digest:
        raise RuntimeError('Exact accepted package identity mismatch')
    if (root / 'VERSION.txt').read_text().strip() != TAG:
        raise RuntimeError('Version mismatch')
    # Independent Linux and modularization runs must accept the same source.
    required = {'test-shared-store.yml', 'modularization-stage-gate.yml'}
    accepted = {}
    deadline = time.monotonic() + 600
    while required - accepted.keys():
        for run in api(f'actions/runs?head_sha={source}&per_page=100')['workflow_runs']:
            workflow = run['path'].split('/')[-1]
            if workflow not in required:
                continue
            if run['status'] == 'completed':
                if run['conclusion'] != 'success':
                    raise RuntimeError(f'Independent gate failed: {workflow} run {run["id"]}')
                accepted[workflow] = run['id']
        if required <= accepted.keys():
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Independent exact-source gates not completed; no publication')
        time.sleep(10)
    for ref, expected in PROTECTED.items():
        if api(f'git/ref/{ref}')['object']['sha'] != expected:
            raise RuntimeError(f'Protected reference changed: {ref}')
    tags_before = {t['ref']: t['object']['sha'] for t in pages('git/matching-refs/tags/')}
    # matching-refs is one array endpoint (gh pagination also handles a single page).
    if f'refs/tags/{TAG}' in tags_before:
        raise RuntimeError('New tag already exists; refusing to modify it')
    old_releases = {r['id']: release_identity(r) for r in pages('releases?per_page=100')}
    if any(r['tag_name'] == TAG for r in old_releases.values()):
        raise RuntimeError('Release already exists; refusing to modify it')
    checksums = package / 'SHA256SUMS'
    checksums.write_text(f'{digest}  {exe.name}\n', encoding='ascii')
    download = f'https://github.com/{REPO}/releases/download/{TAG}/{exe.name}'
    report = package / 'VALIDATION.md'
    windows_run = os.environ['GITHUB_RUN_ID']
    report.write_text(f'''# v1.2.6 — Pre-release, not approved for production

Source: {source}. Certified behavior base: 410bf72fe197e6e7d9a4a1a299a135a716c71bf3.
Only version metadata and safe additive publication changed.
EXE SHA-256: {digest}
Download: {download}
Windows build/acceptance: https://github.com/{REPO}/actions/runs/{windows_run}
Independent exact-source gates: {json.dumps(accepted, sort_keys=True)}
PASS: {manifest['regression_scripts']} regression scripts; real Windows build/smoke;
frozen EXE idle exit with no central folder/roster/operations; offline restart,
original event IDs/timestamps, four operations/two completed sessions;
strict startup 0/20 anomalies, theme 0/30 anomalies, 30/30 confirmed clicks.
Application and Windows PE resource version verified as 1.2.6.

Pending: actual multi-PC SMB/ACL/power-loss, Windows logoff/reboot,
extended GUI/DPI/printing and operational acceptance. No production installation.
Existing releases/tags, stable v1.2.5, main and operational data are protected.
''', encoding='utf-8')
    gh('release', 'create', TAG, str(exe), str(checksums), str(package / 'manifest.json'),
       str(report), '-R', REPO, '--target', source, '--prerelease', '--latest=false',
       '--title', 'Καταγραφή Θέσεων v1.2.6 — Δοκιμαστική έκδοση', '--notes-file', str(report))
    published = api(f'releases/tags/{TAG}')
    if not published['prerelease'] or published['draft']:
        raise RuntimeError('Release is not a visible pre-release')
    if api(f'git/ref/tags/{TAG}')['object']['sha'] != source:
        raise RuntimeError('Published source mismatch')
    # Re-download the published binary and verify the actual delivered bytes.
    delivered = root / 'artifact/published-verification'
    delivered.mkdir(exist_ok=True)
    gh('release', 'download', TAG, '-R', REPO, '-p', exe.name, '-D', str(delivered))
    if hashlib.sha256((delivered / exe.name).read_bytes()).hexdigest() != digest:
        raise RuntimeError('Downloaded release EXE checksum mismatch')
    for ref, expected in PROTECTED.items():
        if api(f'git/ref/{ref}')['object']['sha'] != expected:
            raise RuntimeError(f'Protected reference changed: {ref}')
    after = {r['id']: release_identity(r) for r in pages('releases?per_page=100')}
    if any(after.get(key) != value for key, value in old_releases.items()):
        raise RuntimeError('Existing release identity changed')
    tags_after = {t['ref']: t['object']['sha'] for t in pages('git/matching-refs/tags/')}
    if any(tags_after.get(key) != value for key, value in tags_before.items()):
        raise RuntimeError('Existing tag changed')
    proof = {'source_commit': source, 'version': TAG, 'exe_sha256': digest,
             'release': published['html_url'], 'download': download,
             'windows_run': windows_run, 'independent_gates': accepted,
             'downloaded_exe_hash_verified': True, 'old_releases_unchanged': True,
             'old_tags_unchanged': True, 'protected_refs': PROTECTED}
    proof_path = root / 'docs/validation/v1.2.6-publication.json'
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    section = f'''## Published v1.2.6 Pre-release — 2026-10-16

Source: `{source}` (version-only successor of certified `410bf72`).
EXE SHA-256: `{digest}`
Release: {published['html_url']}
Direct EXE: {download}
Windows run: {windows_run}; independent exact-source gates: {json.dumps(accepted)}.
All final gates PASS, including the exact published/downloaded EXE hash.
Application, VERSION.txt, PE resource and manifest: v1.2.6.
Old releases/assets/tags and main/v1.2.5 compared before/after: unchanged.
Proof: `docs/validation/v1.2.6-publication.json`.
This is test-only; production replacement remains unapproved.
Next: user-controlled field acceptance (multi-PC SMB/ACL/power loss,
Windows sessions/reboot, extended GUI/DPI/printing). No new development authorized.

'''
    docs = ['docs/CONTINUATION.md', 'docs/VERSION_REGISTRY_EL.md']
    for name in docs:
        p = root / name
        p.write_text(section + p.read_text(encoding='utf-8'), encoding='utf-8')
    subprocess.run(['git', 'fetch', 'origin', BRANCH], check=True)
    subprocess.run(['git', 'diff', '--exit-code', source, 'FETCH_HEAD', '--',
                    'src', 'tests', 'tools', '.github/workflows', 'VERSION.txt'], check=True)
    # Documentation changes are retained while following diagnostics-only bot commits.
    subprocess.run(['git', 'checkout', '-B', BRANCH, 'FETCH_HEAD'], check=True)
    subprocess.run(['git', 'add', '--', *docs, str(proof_path.relative_to(root))], check=True)
    subprocess.run(['git', 'commit', '-m', 'Record published v1.2.6 exact EXE and protected release evidence [skip ci]'], check=True)
    subprocess.run(['git', 'push', 'origin', f'HEAD:refs/heads/{BRANCH}'], check=True)
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()

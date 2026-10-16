# Exact continuation checkpoint — 2026-10-16, active final verification

The user explicitly resumed the task on 2026-10-16. The STOP instruction from
2026-10-15 is superseded. Work exclusively on
`feature/v125-modularization-20261013`, using the existing Python 3.12 `.venv`.
No reinstall, new worktree, production deployment or main modification.

## Current state — do not repeat completed modules

Structural modularization is complete: 43 source files, entry 88 lines,
MainWindow composition 77 lines, largest module 366 lines. All legacy APIs/data
formats remain. New real Qt workflow and architecture contracts pass.
Latest code/configuration commit: `d128e6db8cde73b174b8fb20020228058c9daf7a`.
Source-only tree: `da3f565224a4b973c2b702c462402447fc5f1f1b`.
Composition extraction: `9ac9eb9d921cb5c0dbf17f015054ff82ce2f4431`.
Real Qt workflow: `dd170354aa9b705f09456c875037442bb051a24b`.

Full local **43 scripts PASS**, compileall src/tests/tools and git diff --check
PASS. Four native Windows process/fixture cases skip on Linux. External native
EXE driver is Windows-only and was not executed locally.

Current final workflows for exact d128e6d:

- Linux **38868080997 PASS**.
- Modularization gate **38868081064 PASS**.
- Windows **38868081099 PENDING**: build, smoke, NEW external EXE offline/restart/
  online mouse/keyboard workflow, strict visual test and gated artifact upload.

**First next action:** inspect completion of Windows 38868081099, fetch its
Git diagnostic commit and verify report provenance, actual functional results,
strict 20-start/30-toggle metrics, EXE hash and artifact upload. Do not claim PASS
or a final artifact until all of these finish. If failed, diagnose the retained
actual error/screenshots and correct that small cause; do not start more modules.
Then update this checkpoint and `MODULARIZATION_REPORT_EL.md` with exact results.

## Already certified presentation correction

Last complete native SUCCESS:
`b943a8693a3eed2329dc8b1fc4601afe4e0990a3`.
Windows **38865827943**, Linux **38865827783**, gate **38865827824** all PASS.
Windows: 41 regressions, EXE build/smoke, strict startup **0/20**, theme **0/30**,
actual clicks **30/30**, successful artifact upload (60.5 MB test EXE).
That revision precedes the final controller extractions/new external EXE test;
do not transfer its whole-build certification to d128e6d.

Artifact:
`POSITION_TRACKING_WINDOWS_TEST-b943a8693a3eed2329dc8b1fc4601afe4e0990a3-38865827943`.
Run: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38865827943

Actual cause/evidence: initial desktop mismatch consisted of 1,043 console-border
focus pixels; other frames were genuine completely white native surfaces before
first Qt paint. Owned CI background now has its own Win32 message thread and is
activated before each reference. Native initial presentation now waits, DWM-
cloaked, for the real complete Qt backing-store draw and releases once afterward.
This is never used during later theme transitions. No screenshot overlays,
nested event-loop processing or timed exposure delay. All raw frames/distances
retained, original .08 threshold unchanged; only byte-identical INITIAL desktop
may be loading. White/partial/black UI, desktop returning after UI and desktop-only
or zero-frame captures remain failures. All 20 successful starts retained their
exact initial desktop sequence; no failing application frame was excused.

## Exact failures, corrected prerequisites and evidence

- 38806871707 / 22bc3bd: 12/20 startup failures (yesterday's checkpoint).
- 38861912057 / 0f6fee5: 36 regressions/build/smoke PASS, visual FAIL 14 startup,
  1 theme. Application src/ tree exactly matched theme extraction ec80b132.
- 38862995734 / f31fe5c: settings test failed Windows 8.3 versus canonical path;
  corrected expected base.resolve(), preserving actual original path semantics.
  Build/visual did not execute.
- 38863724150 / da9b4d1: 40 regressions/build/smoke PASS, visual FAIL 17 startup,
  zero theme. Ineffective WA_NoSystemBackground was subsequently removed.
- 38865045894 Windows and 38865045885 Linux / 7444dc9: rendering test failed
  because its constructor-scheduled 100ms timer ran at iteration=0, exposed=False.
  Now waits for actual initial root Paint with hard timeout; all 60 synchronous
  per-child paint/config assertions retained. Native visual did not execute.
- Gate 38865045892: backend source inspection accidentally imported Qt. Now AST-
  inspects actual linked controllers without importing UI; python -S handoff
  replay test and full gate pass, with all original ID/order scenarios retained.
- Local static handoff ownership and button quote/whitespace guards were adapted
  to actual inherited method/helper identity and AST Qt constructors; no scenario
  removed. Initial failures and successful reruns remain in local evidence index.

All diagnostic evidence remains under docs/validation/windows-visual-<run>-1 and
linux-<run>-1. Local stage results/failure logs: docs/validation/local-20261016/.
Architecture audit verifies all 66 store methods and 50 effective UI methods versus
0f6fee5 (normalizing only explicit path providers); constructor tested through GUI.
See docs/validation/structure-20261016/{ast-audit,modules,commits}.json.

## Architecture and preserved correctness

Read MODULARIZATION_REPORT_EL.md for all 43 file responsibilities and test matrix.
No module imports entry; graph is acyclic; backend/report modules import without
entry/Qt/optional document libraries. Entry preserves legacy exports and config
path overrides. Store/UI capability mixins compose into small facades, with
WindowServices supplying runtime providers. JSON/SQLite/receipts/timestamps,
START/END link identity, filenames, report contents, theme data and assets remain
compatible. Earlier durable START ACK-loss and atomic APPLIED/cache fixes remain
and pass their fault/retry contracts. No new module work is pending.

Actual Qt workflow passes offline EXIT 14 START/END, close/reopen, original-ID/time
replay, online ENTRY 1 START/END, two history sessions, archive/map dialogs and
wrong-PIN rejection. New EXE workflow must prove these with native mouse/keyboard
against the frozen binary and temporary data before packaging.

## CI and artifact access

Git HTTPS works. GitHub API/artifact-download tunnel is blocked; public Actions
pages show actual status/artifact names. CI safely appends diagnostics to this
same branch only if source/tests/tools/workflows still match its tested commit;
docs-only parallel progress is allowed. Fetch and preserve bot commits; rebase
only unpublished commits, never force-push. Do not ask the user to retrieve logs
while this supported Git evidence route works.

Accepted EXE packages require all regressions, strict visuals AND functional
report with the same source SHA/EXE SHA256. Upload failure is not ignored. They
contain EXE, SHA256SUMS, manifest and regression/visual/functional reports;
retention 7 days, no release/tag. Failure reports and screenshots are retained
also for failed native functional workflow.

## Remaining real acceptance and protection

Real multi-PC SMB/NTFS ACL, power loss, Windows account/session/logoff/reboot,
10:00 boundary, extended responsiveness/shutdown during blocked SMB, cached cold
launch, high-DPI/small displays and actual printing remain FIELD acceptance.
Simulations do not certify those. Use test data; no operational dataset authorized.

Main remains `3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`.
v1.2.5 tag remains `33ea13ca2133ddbfb93b1d051d4b25dc35bd954f`.
release/, VERSION.txt and production release workflow unchanged from 129e8cb.
No main/production binary/tag/release/data changes or merge performed.

Do not rerun passed checks for identical code without a new change/failure.
If a source correction is necessary, run its focused repro plus full suite:
`XDG_CACHE_HOME=/tmp/tde-cache .venv/bin/python tools/run_regressions.py --out /tmp/tde-next`;
then compileall/diff check and new native CI, retaining failures/provenance.

## Latest native failure and corrective fixture checkpoint

Windows 38868081099/d128e6d completed FAIL after 43 regressions/build/smoke PASS.
External EXE correctly recorded offline START/END on EXIT 14 with original END
link, then failed during restart/cleanup. Its driver left read-only sqlite3
connections open (`with Connection` does not close it), causing Windows WinError32
and potentially masking the original workflow exception. No final visual or
accepted EXE package was produced for this run. Evidence retained at
validation/windows-visual-38868081099-1/functional-report.json and screenshots.

Corrective change is TEST DRIVER ONLY: explicitly close both readers, preserve
original workflow/launch exception and screenshot before temporary cleanup.
New portable fixture contract checks actual close and unchanged row identity.
Full **44 scripts PASS** (/tmp/tde-exe-reader-close-20261016), compileall/diff PASS.
Application src/ tree remains da3f565224a4b973c2b702c462402447fc5f1f1b.
First action is now inspect the corrective run, not repeat modules. Diagnose any
remaining ORIGINAL error rather than treating a cleanup failure as application
corruption or claiming the frozen workflow passed.

# Safe paused checkpoint — 2026-10-16

PAUSED by explicit user instruction because of the remaining Codex quota.
Do not resume development, tests, builds or Actions until the user resumes work.
No new tests or Actions were started to create this checkpoint. The already
running Windows Action may finish independently; it was not cancelled.

## Exact saved state

- Branch: `feature/v125-modularization-20261013` only.
- Last application/test/workflow commit: `762c3a369a199766ab629007b6b2a3c27885d5e1`.
- Last fetched diagnostics commit: `ee3e5e9ff90050249097ea7e94f8c73904605e93`;
  fast-forwarded locally without discarding changes.
- Application src tree: `efa779ebf0a24f02e72125dbc185d857e059493b`.
- This documentation checkpoint's exact SHA is available with
  `git log -1 --format=%H -- docs/CONTINUATION.md` after commit/push.
- Structural modularization complete: 43 source files (entry plus 42 modules),
  entry 88 lines, MainWindow 77, largest module 366. All 226 owned function/method
  annotations resolve. Store/UI AST behavior audit retained in validation docs.
- Latest local suite: **45 scripts PASS**, compileall src/tests/tools PASS,
  diff check PASS. Native Windows-only cases are not certified by Linux runs.
  Existing final local logs/results are preserved in
  `docs/validation/local-20261016/recovery-contract-budget/`.

## Last Actions for exact code commit 762c3a369a199766ab629007b6b2a3c27885d5e1

- Linux **38874685771 PASS**; committed results:
  `docs/validation/linux-38874685771-1/results.json`.
- Modularization gate **38874685792 PASS**.
- Windows Qt recovery diagnostic **38874685760 PASS, 8/8**; logs/provenance:
  `docs/validation/ui-recovery-38874685760-1/`.
- Full Windows **38874685744** was in progress at last observed Actions status.
  During checkpoint push, CI committed its diagnostics in `ee3e5e9ff90050249097ea7e94f8c73904605e93`;
  these were integrated without overwriting changes. Preserved visual report:
  startup endpoint anomalies **0/20**, initial exact desktop loading **20/20**,
  theme endpoint anomalies **0/30**, confirmed clicks **30/30**.
  External frozen EXE functional report **PASS**: four operations, two completed
  sessions, original IDs/timestamps preserved, temporary data only.
  EXE SHA256: `beb836483229f3656e959c0891a7bd27cb7f58a0813b2bfa1015dabbf27699f7`.
  Evidence: `docs/validation/windows-visual-38874685744-1/`.
  Overall final Actions status and accepted artifact upload remain unverified;
  do not claim overall PASS or availability until checked on resumption.
  No waiting or new run was initiated for this checkpoint.

## Last known failure and completed correction

Windows **38872859841**, commit
`f4af1bddfbc628d6ad3926b50fb6940c33a0bcf6`, passed 44 regressions, build/smoke
and the external frozen EXE data workflow: four receipts, two sessions, original
IDs/timestamps preserved. Overall Action still FAILED after the successful
functional JSON report: its Greek console JSON was incompatible with the
Windows command pipe encoding. ASCII-safe console output now retains UTF-8
report files, with a real cp1252 regression. That earlier run did not execute
visual acceptance; its functional PASS is not an overall PASS.

An earlier Qt recovery timeout (38870905825) had insufficient diagnostic state;
its exact historical host delay cannot be established retrospectively. The old
12-second test deadline was shorter than the existing backend lock contract
(10-second schema lock + 15-second handoff lock + polling). The recovery-only
budget now derives from those limits (31 seconds). A controlled real 13-second
OS lock reproduced recovery beyond the old deadline: 14.854 seconds with 297
responsive Qt heartbeats, four receipts/two sessions and unchanged data checks.
Eight latest Windows diagnostic repetitions passed. Visual criteria and ordinary
input deadlines were not relaxed. Preserve all original failed reports.

## First action on explicit resumption

Read this checkpoint, then inspect the existing Windows run **38874685744** and
newer remote diagnostic commits. Fetch/fast-forward without losing changes.
Verify exact source provenance, functional report, all regressions, strict
20-start/30-theme metrics, EXE SHA256 and actual accepted artifact upload.
Expected artifact name, only if genuinely uploaded after acceptance:
`POSITION_TRACKING_WINDOWS_TEST-762c3a369a199766ab629007b6b2a3c27885d5e1-38874685744`.
Do not repeat completed modules or successful checks for unchanged code.
If that run failed, diagnose its preserved error before deciding on a small fix.

Remaining: finish native acceptance of the complete modularized candidate;
update final technical report and artifact/hash references with actual results.
`MODULARIZATION_REPORT_EL.md` and older audit/plan status lines predate the latest
candidate; this checkpoint takes precedence for current verification status.
Real multi-computer SMB/Windows-user/offline/service-data acceptance remains
UNEXECUTED; follow `docs/FIELD_ACCEPTANCE_EL.md` using isolated test data first.
No main/stable v1.2.5/release/real service data changes or production deployment.

Historical evidence below is retained; historical pending statuses are superseded
by this paused checkpoint and are not current certification claims.

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

## Driver fixture and interface corrections already saved

d128e6d/Windows 38868081099: 43 regressions/build/smoke PASS, external driver FAIL.
Two real offline EXIT 14 operations were durable. Its unclosed read-only SQLite
connections caused WinError32 during cleanup and hid the original workflow error.
Both readers now close explicitly; exception/screenshots survive cleanup.

f44331e/Windows 38869909515: 44 regressions/build/smoke PASS; original error now
visible: cannot activate owned test background after native keyboard input. No
second EXE was launched, no central data existed and pending IDs/times were intact.
Corrected cross-thread WM_NULL acknowledgement and checked temporary input-queue
attachment/detach are in e243e53. Linux 38869909478 and gate 38869909506 PASS.

Type-contract audit restored SharedEventStore, dtime/date and Path imports in
three extracted modules. All 226 annotations resolve. Full local 44-script suites
for reader, type and foreground fixes PASS; see saved local stage evidence.
These were small verified corrections, not another module cycle. Final native
result is still required. Full isolated field protocol: FIELD_ACCEPTANCE_EL.md.

## Latest unreproduced Windows Qt recovery failure — do not waive

Windows 38870905825/e243e53 failed before build/EXE in ui_workflow_regression.py:
the second-window store/pending replay condition did not finish within the
unchanged 12s deadline. No diagnostic state was previously printed. Other
regressions, Linux 38870905814 and gate 38870905823 PASS. Current native foreground
fix has NOT yet reached the external EXE step, so it is not certified.

Added timeout diagnostics: info/status, handoff error, pending/conflict/applied
rows, actual timer state and future outcome. Eight controlled fresh-process
Linux repetitions PASS (/tmp/tde-ui-recovery-repro.json), plus full 44-script suite
PASS (/tmp/tde-recovery-diagnostics-20261016), compileall/diff PASS. No timeout,
assertion, scenario or failure criterion relaxed. A separate bounded Windows
recovery diagnostic workflow now executes up to eight trials, stops at first
failure and preserves exact logs/provenance through Git. This is diagnostic work,
not a replacement for the full native EXE/visual acceptance pipeline.
First action: recover that Windows diagnostic state and fix its evidenced cause.

f4af1bd: bounded Windows recovery diagnostic 38872859978 PASS all eight attempts;
Linux 38872859829 and gate 38872859906 PASS. Windows 38872859841 ran 44 regressions,
build/smoke and the ACTUAL frozen EXE offline/restart/online data scenario PASS:
four original receipts, two sessions, IDs/timestamps preserved, binary SHA256
243b70a56332067da0f06df1bd24ccaa074d5cb11ef4de3101ce6ac14d873c85.
Workflow nevertheless FAILED after its successful functional report was written;
visual did not run. Sole remaining CLI operation was printing unescaped Greek
JSON to a Windows command pipe. New portable regression reproduces cp1252 console
encoding and verifies ASCII-safe JSON output plus unchanged UTF-8 evidence file.
44 local scripts PASS (/tmp/tde-exe-console-encoding-20261016), compileall/diff PASS.
This is a driver reporting correction, not a waiver of its nonzero exit status.

Recovery timing contract correction is evidenced, not an arbitrary timeout
relaxation: production permits 10s schema-lock + 15s handoff-lock waits, with 3s
poll delivery. The new test's old 12s end-to-end assumption was invalid. Recovery
budget now derives from those bounds (10+15+2*3 = 31s), while all ordinary input
waits stay 12s and every receipt/ID/time/assertion remains. A NEW real OS-held
handoff lock lasting 13s proved the counterexample: recovery 14.854s with 297 Qt
heartbeats, four preserved receipts/two sessions, no UI freeze or data loss.
The original intermittent Windows timeout had no historical state diagnostics;
no claim is made that its exact old host delay was recovered retroactively.
All subsequent timeouts retain the full state; all eight bounded Windows trials
on f4af1bd passed even before this budget correction.

Full **45 scripts PASS** (/tmp/tde-recovery-contract-budget-20261016), compileall
src/tests/tools and diff PASS. Strict visual .08/20 starts/30 toggles unchanged.
Application src/ tree still efa779ebf0a24f02e72125dbc185d857e059493b. Await final
native validation of these TEST/DRIVER corrections; do not declare completion yet.

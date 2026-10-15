# Modular development — continuation checkpoint

Work only on `feature/v125-modularization-20261013`. Do not modify main,
production v1.2.5, real operational data, or publish a production release.
Use the existing checkout and installed Python 3.12 `.venv`; no reinstall or
worktree is needed. User's full instruction is to complete fixes, modularization,
tests and a development EXE autonomously, with small verified changes.

## Baseline and unresolved gate

- Remote baseline verified: `129e8cba8f9571c099bd46a11f6b979c741951b7`.
- Protected main: `3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`.
- Baseline: 29 local scripts PASS, module gate 38794439749 PASS.
- Full Windows 38794439758 failed its visual test. User examined its images:
  toggle 24 shows upper widgets already light, bottom buttons still dark;
  30/30 theme clicks activated. This is evidence of a mixed frame, not a reason
  to relax thresholds. Earlier 38788459409 also had 6/20 startup anomalies.
- Artifact 12001517568 was uploaded successfully (39.2 MB). GitHub API/artifact
  download is blocked in this cloud session. Public github.com Actions pages
  expose status and job annotations. Do not wait for artifact credentials when
  reported evidence and controlled repeats allow further diagnosis.
- Historical full Windows SUCCESS: b58b5b7, run 38787513005, but its theme test
  preceded the fix for false-green theme clicks. It does not certify the current
  visual criteria. No commit yet has verified full PASS under the new criteria.

## Candidate correction and reproducible checks

`position_tracking_rendering.coherent_widget_update` suppresses updates once at
the top-level window, finishes polish/layout and synchronously repaints the whole
widget tree when reenabling. No event-loop pumping, hiding, overlay or screenshot
mask. `_apply_theme` uses it instead of independently reenabling root/window and
only queuing `update()`. Production version and visual limits are unchanged.

`tests/rendering_regression.py` exercises synchronous paint of upper/lower widgets,
nested/disabled/exception states, no queued-action reentry, and 60 real application
theme changes with persisted configuration in temporary directories. The old
129e8cb application fails this paint-order contract; the candidate passes locally.
This demonstrates a scheduling difference, not yet Windows flicker elimination.

From repository root:

```sh
XDG_CACHE_HOME=/tmp/tde-cache .venv/bin/python tools/run_regressions.py --out /tmp/tde-validation
.venv/bin/python -m compileall -q src tests tools
git diff --check
```

The runner executes every portable test script separately and records exact exit
codes/logs. The Windows-only desktop EXE visual test is a separate mandatory CI
step. Full portable suites now run in Windows build and Linux push CI; module
gates remain separate. Visual artifacts upload even on failure, with one-day
retention. Inspect and record the exact commit/run results after pushing this
candidate. If Windows fails, diagnose and fix this step before further extraction.

## Remaining work after the gate

### Confirmed independent persistence defect (synthetic reproduction)

In `SharedEventStore.start`, inject `_atomic_json` so it performs the active-file
replace successfully, then raises `ConnectionError` to represent a lost server
acknowledgement. The exception handler unconditionally deletes the START event
file. The active marker is still present. Retrying with the original operation
ID returns that active marker without restoring the deleted START history.
Reproduced locally using temporary directories, `PersonnelRecord('999001',...)`,
position 1 / ΕΙΣΟΔΟΣ and fixed event ID `audit-lost-active-ack`; `iter_all_events()`
is empty both before and after retry while the active marker exists. This is not
covered by the existing stage-4 tests, which lose acknowledgement after the whole
store call rather than during active-marker commit. Add a dedicated fault test
and repair the ambiguous-commit path as the next independent correctness change
after the rendering gate. Preserve existing before-write failure semantics and
avoid phantom history, deleted durable records or duplicate ownership.

### CI diagnosis in progress

Candidate application commit `099e61d`; local 30/30 scripts PASS, including four
real Qt rendering contracts. Windows run `38798943639` and module gate
`38798943771` were started. Module gate passed. Full Linux run `38798943593`
failed the portable suite, exact script not available from public annotation.
Diagnostic-only workflow commit `e4a30b5` reruns Linux and saves results plus failed
logs under `docs/validation/linux-<run>-<attempt>` using an append-only evidence
commit on this branch. Fetch/fast-forward it, diagnose that exact failure before
proceeding. Its failure must not be treated as a full Linux PASS.

Subsequent diagnostics were recovered over Git (no user file transfer required):

- `docs/validation/linux-38799602304-1`: three Qt tests could not import
  `libEGL.so.1`. The Linux CI now installs `libegl1` and `libopengl0` before tests.
- `docs/validation/windows-visual-38799602323-1`: 29/30 portable scripts passed;
  `simulated_shared_host_shortcuts.py` failed because a nested station's Greek
  JSON error could not encode to cp1252 in the new captured-pipe runner. The
  runner now sets PYTHONUTF8/PYTHONIOENCODING and decodes UTF-8 explicitly, with
  `runner_encoding_regression.py` verifying nested Greek JSON round-trip.
- Neither failure reached the actual Windows visual step. The rendering
  correction is still pending physical Windows visual validation.
- Both platform evidence writers now append at the current branch tip only if
  tested source/configuration is identical; docs-only diagnostic commits from
  another platform are retained. Failed logs use `.txt` because `.log` is ignored.

Read `ARCHITECTURE_AUDIT.md` for responsibility/dependency/coverage inventory.
Extract one coherent unit per change; preserve legacy entry-point exports and
data/path semantics. Suggested sequence: personnel/value models and OOXML import;
settings/runtime paths; store communication/locking, active positions, shifts and
history; reports; Qt assets/theme/views/controllers; reduce entry point to wiring.
Use explicit dependencies rather than importing the entry point from modules.
Run all portable checks and required Windows visual/build gates between changes.
Add meaningful contracts for newly isolated responsibilities, avoiding circular
imports and forwarding large modules under a new name without actual boundaries.

Keep this checkpoint current with exact SHAs, run IDs and first pending action.
Do not claim completion until full modularization, valid Windows/Linux checks and
development EXE functional scenarios succeed. Real multi-machine SMB/ACL/session
and extended field-use tests must be reported separately, not equated with local
simulations. Production publication remains a separate human approval.

## Rendering gate completed; next correctness change

Full application/code commit `9dbbb21fce2e9f9d938fca6659f01cdeeffecc62`
passed Windows run `38800196045`, Linux `38800195521`, module gate `38800195516`.
Evidence is in `docs/validation/windows-visual-38800196045-1` and Linux equivalent.
31/31 scripts passed on both platforms. Windows EXE build/smoke PASS; startup
endpoint anomalies 0/20; theme endpoint anomalies 0/30; theme clicks 30/30.
The legacy per-frame theme-difference metric is diagnostic only, as before;
normal intended light/dark transitions still register there. Acceptance rules
were not changed. Contact sheets were inspected; the rendering correction is
verified for this run, without claiming permanent/field-wide absence of flicker.

Current next change: `start_marker_ack_regression.py` adds three actual store
fault scenarios. Baseline loses START history in both after-commit cases.
`SharedEventStore.start` now deletes the event only after confirming no active
marker and an accessible active directory; an existing/unreadable marker or an
uncertain share preserves the event and rethrows the original failure. Retry
uses the original operation ID; before-commit no-phantom behavior is preserved.
Run full local/Windows/Linux gates before marking it complete or extracting the
next module. This does not claim SMB server power-loss durability in the field.

## Current checkpoint: fresh-process visual validation

START correction commit `c81b91aa3fc7153ce5a2e1dd9893af05f5ef50a8` passed
32 portable scripts on Linux run `38801316804` and Windows run `38801316650`,
plus module gate. The full Windows run nevertheless FAILED: 9/20 startup
endpoint anomalies, 0/30 theme anomalies, 30/30 confirmed toggles. Do not call
this a full PASS. Last full successful workflow source remains `9dbbb21`.

Evidence was recovered directly over Git, inspected at
`docs/validation/windows-visual-38801316650-1/contact_01.png` and `contact_04.png`.
The first captured startup frame is the runner desktop/console, followed by the
application; other suspect startup pairs show a layout/position change. The
test's `wait_for_window(pid)` ignored its PID and `find_position_window()` selected
any matching title. Terminating only the PyInstaller bootloader could leave its
application child alive. A successful previous startup count therefore does not
prove all 20 windows belonged to fresh launches. This limitation was identified
during the broader audit and must be repaired before trusting that criterion.

The current test-only correction filters HWND ownership to the launched process
tree (including the onefile child), uses pointer-sized Windows API arguments,
terminates the whole owned process tree, and records root/window PIDs and before/
after client geometry. No capture frame, interval, endpoint threshold or failure
condition was removed. `tests/visual_process_regression.py` includes portable tree
logic and actual Windows Toolhelp/taskkill contracts (two native cases explicitly
skip on Linux). The next action is full CI, then inspect exact images/geometry if
startup failures remain. Windows job bounded at 25 minutes to avoid unbounded
resource usage. The existing rendering correction still has zero theme endpoint
anomalies over the two measured 30-toggle runs; that is evidence for those runs,
not a general guarantee.

## Additional confirmed offline recovery defect to fix next

`OfflineJournal.sync` marks an operation APPLIED in one SQLite transaction, then
calls `remember` in another. Reproduced with a synthetic START: make `remember`
raise after the central call and APPLIED write, then reopen the journal. Central
active exists, `pending_count()==0`, but `local_active(agms) is None`. The END
variant can retain stale local active state. Fix the status/observed write in one
transaction, and prevent an already-APPLIED stale concurrent replay from
overwriting newer observed state. Add interruption and concurrency regressions.
Do this as its own verified correctness change before the personnel extraction.

Personnel import compatibility tests have been exercised against the old code
in `/tmp/tde_personnel_contract.py` (4 PASS): Greek headers, leading-zero IDs,
duplicate merging, known-ID/headerless roster, immutable records and invalid
files. Move/adapt them into tests when extracting that independent module. Do
not treat the module as implemented; it is still inside the main source.

### Independent offline transaction candidate (not yet Windows-certified)

Implemented `_record_applied` in `position_tracking_offline.py`: conditional
PENDING→APPLIED and the `observed` update now share one SQLite transaction.
An already completed operation cannot overwrite a newer cached state when an
old worker finally returns. `offline_applied_cache_regression.py` verifies START
and END cache-write failures with a real SQLite abort trigger, reopen/retry with
the same IDs, and deterministic concurrent replay where a late START response
arrives after another process has already applied END. All three tests fail on
the pre-fix offline module and pass on the candidate. Full local suite: 34 scripts
PASS, including two Windows-native cases explicitly skipped on Linux.

This is independent recovery work while fresh-window visual validation of
`fcc315e` runs in Windows. Do not claim the transaction candidate Windows-tested
until its own full CI completes. Preserve the native-test results first: fetch
the diagnostic-only remote commit; rebase this unpublished local correctness
commit on top if necessary (only docs are expected remotely), then push this
branch and require its full portable/Windows checks. If startup anomalies remain,
inspect bbox/PID metadata and images rather than changing thresholds. Continue
fixing the true source of movement/paint or capture misidentification; then resume
the personnel/domain extraction. No production release is authorized.

# Issue #10 — Phase B direct-central operator preview

**FROZEN / UNSAFE TO DEPLOY:** see `ISSUE_10_STALE_WORKER_STOP_20261027.md`.
Two additional stale-worker assertions fail, and Linux CI exposed a Qt shutdown
crash. The local PASS results below predate the additional safety gate; the
overall candidate is FAIL. No further functional development follows this stop.

**TEST ONLY / PARTIAL PHASE B.** The central recovery gate passed first in
`2599257440a9e8b46b770f1ef4ef21a092b44e42`. This checkpoint adds a runnable
operator path; it is not the complete Issue #10 application and is not approved
for a production share. No EXE, release or installation is supplied.

## Preview entry and data

From this source checkout, with the normal dependencies installed:

```text
python src/position_tracking.py --central-only
```

The flag is deliberate: the default legacy application remains available while
officer/report functions are being migrated. **Do not run that default legacy
application against the candidate store.** The preview does not instantiate its
MainWindow, OfflineJournal, local settings, diagnostics or bootstrap lifecycle.
No new desktop shortcut, local EXE, local roster or business database is created.

The preview reads shared `.tde_runtime/position_tracking.settings.json` beside
the application. An explicitly configured `central_root` is honored; otherwise
the existing shared `.tde_runtime` directory is used. The root must already
exist: an unreachable share never produces a local fallback store. Personnel
comes from central `personnel.xlsx`, or the existing central `CONFIG` / application
directory `ΠΡΟΣΩΠΙΚΟ` / `PROSOPIKO` workbook. Personal saved roster paths and
per-Windows-user copies are ignored. No real service files were opened in tests.

Old deployed outboxes are preserved and are not opened by this operator path.
Read-only inventory and verified officer reconciliation before any field cutover
remain required; this preview is not a migration tool and does not claim that
pending historical queue entries were incorporated.

## Behavior and bounds

- AGMS lookup reads centrally sourced identity/active position in a worker.
  END binds the exact centrally observed START ID; it never ends a replacement.
  An active worker can END even if its old roster row/file is no longer available.
- START/END writes are direct central operations with stable immutable request
  IDs/timestamps. START does not wait for shift synchronization. On lost ACK the
  original ID is read back; no second mutation is replayed in that read-back.
- One read worker and one action worker each accept one running job and **zero
  waiting jobs**. UI timers only inspect local Future state; there is no automatic
  central polling, offline timer, sync conflict dialog or presence announcement.
  Keystrokes coalesce to the latest selection; stale results cannot enable buttons.
- After 3 seconds the UI displays the required unconfirmed message. The running
  worker remains owned; timeout never cancels it or permits another action.
  Unknown outcomes block mutations until explicit recheck of the original ID.
- Exit does not END any position. Reopen and changing Windows accounts preserve
  the confirmed central START. An in-flight exit warning states uncertainty;
  it does not claim the worker or write was cancelled.

## Validation

- **PASS** original END interruption gate: 4/4, assertions unchanged.
- **PASS** central recovery: 24/24, including process death and 15-client races.
- **PASS** direct-central service/worker tests: 11/11.
- **PASS** real headless Qt operator tests: 6/6. Includes blocked reads/writes,
  UI event delivery, 100 repeated attempts without queuing more work, selection
  coalescing, unknown outcome/recheck, actual button START/END, app/account reopen
  and a real subprocess launch with local/legacy providers forbidden.
- **PASS** full portable regression runner: 55 scripts, zero failing scripts.
  Existing legacy tests are compatibility checks, not evidence that the legacy
  runtime now follows central-only semantics. Windows-only skips remain NOT RUN.
- **PASS** Python module architecture gates, workflow YAML parsing and diff checks.
- **NOT RUN locally** actual Windows source behavior, packaged EXE, real SMB
  interruption, multiple physical terminals or field acceptance.

Commands used with Qt tests:

```text
PYTHONPATH=/tmp/tde-issue10-deps QT_QPA_PLATFORM=offscreen python tools/run_regressions.py --out /tmp/tde-issue10-phase-b-results
```

The isolated branch now has a read-only-permission Linux/Windows **source** CI
workflow. The legacy EXE workflow skips this branch and its PRs: the operator-only
preview is not ready for packaging. CI run identities/outcomes are recorded in
the subsequent validation checkpoint; a configured workflow alone is not PASS.

## Concise changelog and remaining work

Added direct-central service, one-job workers and opt-in operator UI/entry flag;
added focused service/Qt checks and source CI. The recovery change is a separate
commit, so these checkpoints can be reviewed independently.

Remaining Issue #10 gates: atomic confirmed handover; candidate officer
authorization and centralized roster administration; complete shift/live-position
separation; historical report admission/overlap checks and PDF/history regeneration;
worker isolation of officer/report/map I/O; default-entry switch after those
features are ready; packaged Windows candidate identity and real SMB field tests.
No main, `CURRENT_APPROVED.json`, release binary, production shortcut or queue was
changed. Do not merge, publish or point the preview at production data.

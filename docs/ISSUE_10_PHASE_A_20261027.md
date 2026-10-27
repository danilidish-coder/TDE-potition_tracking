# Issue #10 — Phase A checkpoint, 27 October 2026

**BLOCKED: data-integrity stop condition. Central-only implementation NOT DONE.**

## Identity and authority

- Repository: `danilidish-coder/TDE-potition_tracking`.
- Selected branch before any edits: `feature/central-only-simple-20261027`.
- Initial HEAD and `git merge-base HEAD 4340c41865328cd893e6dc23fcdcedfefa7f9bf2`
  both returned `4340c41865328cd893e6dc23fcdcedfefa7f9bf2`.
- Read Issue #10 (including its stop conditions), `DEVELOPMENT_RULES.md`,
  the historical task document, the active Drive protocol
  `1rfBUTjL5tyu_mdiE4WxM_09gYgN5HFQCMdC1YxrzZ7w`, and app registry
  `1pELYUnX56MaJAC2Xe2tFsBj_ugVURqZzJijpkRtYv-c`.
- The old task's `eed6edab` baseline is not used. Main, approved manifest,
  release assets and production data are outside this checkpoint's changes.

## Read-only diagnosis before edits

1. `position_tracking_ui_main.py` constructs `OfflineJournal`; starts shift,
   communication and offline timers at 3 s, 2.5 s and 3 s respectively.
2. `position_tracking_ui_positions.py::_position_action` enqueues START/END
   locally, then `_offline_tick` calls `reconcile_handoff_before_replay`.
   The latter queues/records automatic END for earlier Windows accounts before
   replay. This violates the new session-independent live-position contract.
3. `position_tracking_machine_queue.py` selects `TDE_POSITION_MACHINE_ROOT`,
   otherwise `PUBLIC/Documents/TDE_Krystallopigis/PositionTracking_Queue` on
   Windows. `TDE_POSITION_LOCAL_ROOT` controls the local root; legacy outboxes
   may exist under its `machine_queue/position_outbox.sqlite3`. The selection
   helper itself creates directories and a write probe: do not invoke it for
   a read-only migration audit. No deployed queues were inspected or changed.
4. Offline journal `operations` holds PENDING/CONFLICT records and `observed`
   holds cached active records. `ui_configuration` also copies rosters locally;
   `_offline_tick` invokes the local EXE bootstrap cache.
5. Central START uses per-AGMS and `__POSITION_START__` locks, event JSON then
   active JSON, followed by shift synchronization. END writes event JSON,
   pending receipt JSON, removes active JSON, indexes history in SQLite,
   then removes the receipt. These are separate commits.
6. Startup reconciliation scans pending receipts only. `_has_end_receipt`
   checks pending receipts only; neither recovers an END that was committed
   just before writing its receipt failed. Exact-ID lookup requires the
   original timestamp's folder and prefix, so a stable ID alone is insufficient.
7. `end_officer_shift` automatically ends approved active positions under
   `__SHIFT_CONTROL__` (20 s timeout). GUI report creation synchronously calls
   `sync_active_shift` and renders PDF. Officer selection looks up a typed AGMS;
   that lookup does not establish authorization for privileged actions.

## Reproduced blocker

Before edits, ran a standalone Python probe importing the real central store
and using only `TemporaryDirectory` and a synthetic person. Injected an OSError
at the pending-receipt write, after the END event was durably written.

Observed after constructing a fresh store:

```text
END events durably present: 1
Position still active after reopen: True
Completed personnel history rows: 0
END events after new client retry: 2
```

Thus central event history says END while active state says occupied and indexed
history has no completed work. A fresh client can write a second END against the
same START. Existing offline replay can repair this only if it retains the exact
original ID and timestamp. Removing that dependency without central recovery
would leave this ambiguity unresolved after process exit or user change.

This triggers Issue #10: **"If baseline/source collision or data integrity
uncertainty: stop, preserve branch and evidence, explain blocker."** No runtime
source changes were made after discovering it.

## Validation and deliverable status

`python tests/central_end_interruption_regression.py`:

- PASS: normal END survives reopening with one history row.
- PASS: replay using exact original ID and time repairs the interrupted END.
- FAIL: reopening alone does not recover the durable END.
- FAIL: another client writes a second END against the same START (`2 != 1`).

These are actual failing assertions, not expected failures or simulated PASS.
Additional baseline checks:

- PASS: `start_marker_ack_regression.py` (3 cases).
- PASS: `shared_file_lock_concurrency_regression.py` (72 attempts, 6 locks).
- PASS: `module_boundaries_regression.py` (3 cases).
- NOT RUN: `personnel_history_sqlite_regression.py` could not import PySide6.
  Dependency installation attempted the read-only user site and failed;
  this is an environment limitation, not a history assertion result.
- PASS: `git diff --check`; no diff in `src`, `release`, `.github`, or
  `CURRENT_APPROVED.json` against the exact approved baseline.

The reproduction models a file-operation boundary; actual SMB disconnection,
Windows packaged EXE, 15 physical clients and field acceptance are **NOT RUN**.
No candidate EXE, Actions build/run ID, binary hash or installation is claimed.
Phases B–E remain **NOT RUN / NOT IMPLEMENTED**.

## Next concrete work

Resolve the central END event/receipt recovery contract first, preserving raw
events and original operation timestamps. A restart must reconcile an already
durable END without relying on the old local queue; another client must not
create a second END for that START. Evaluate START interruption and immutable
operation-ID lookup across day boundaries under the same recovery design.
Make the failing gates pass before removing offline runtime dependencies.
Do not repair real shared data or delete queues as part of these tests.

## Concise changelog

- Added a portable, isolated four-case regression for central END interruption.
- Recorded exact baseline, current queue/lock/report flow and integrity blocker.
- Changed no application behavior, workflow, manifest or approved binary.

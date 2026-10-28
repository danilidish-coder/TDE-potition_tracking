# Issue #10 — Phase D1 checkpoint, 28 October 2026

## Phase D1 continuation from d6969b1 — platform source CI pending

Branch `feature/central-only-simple-20261027`; clean starting checkpoint
`d6969b1e62265857901621c23f4923185ebc6297`, approved ancestor
`4340c41865328cd893e6dc23fcdcedfefa7f9bf2`.
Read the active development guide v2.1 and live Drive app registry, GitHub
Issue #10, repository DEVELOPMENT_RULES.md and CURRENT_APPROVED.json on main.
The approved manifest is absent from this historical feature branch by design;
it was read remotely without copying/changing it. Approved source/EXE identity
is unchanged. Previous Phase C source run `40697620744` remains accepted evidence.

Real isolated SMB availability check: **NOT RUN / unavailable**. No mounted
CIFS/SMB share, configured private TCP destination, VPN or synthetic test-share
credentials/endpoints were available in the managed environment. No service
network was contacted or scanned. The source fault tests below are simulations,
not a replacement for physical SMB interruption/restart acceptance, which remains
mandatory before operational approval and does not block independent D1 work.

Implemented D1 only:

- `position_tracking_shifts.py`: officer shift completion no longer calls
  physical END, no longer requires a matching live-position preview, and keeps
  `closed_active_agms=[]` for compatibility. Wrong shift ID, pending-member
  decisions and shift time-order validation remain enforced. Explicit guarded
  `end_officer_shift_member` is separate and unchanged.
- Membership can be decided before physical START. Officer-only discovery also
  finds committed short work already explicitly ended before the next refresh.
  Membership changes accept an expected shift ID, so late decisions cannot alter
  the next shift. Exclusion/undo changes only membership, never work timestamps.
- `position_tracking_positions.py`: physical START never calls shift sync or
  waits on `__SHIFT_CONTROL__`, including legacy sync_shift=True callers.
- `position_tracking_handoff.py`: central Windows identity-change compatibility
  hook is a no-op; it cannot generate END or mutate/read central work. Historical
  offline code/queues remain isolated and untouched; no queue is activated.
- `position_tracking_event_queries.py`: existing shift session projection uses
  durable events as of the report boundary, so later actual END/handover cannot
  erase prior shift work. The report clip is not a physical END. No new historical
  admission/report feature was started.
- Existing GUI modules `position_tracking_ui_shifts.py`, `_ui_admin.py`,
  `_ui_shift_end.py`, `_ui_lifecycle.py`: one owned worker without a waiting
  queue runs shift reads/start/membership operations. The existing completion
  modal allows open positions and clearly states they remain active; its implicit
  bulk-END completion path was removed. Explicit single END remains separate.
  No new officer panel, authorization design, D2 or packaged candidate was built.

New targeted tests: `central_shift_separation_regression.py` **11/11 PASS**;
real Qt `central_shift_ui_regression.py` **5/5 PASS** locally. Cover open-position
shift changes, exclusion/undo, approval before START, short-work discovery,
stale shift decisions, simultaneous physical writes while shift control or slow
shift persistence is held, failed finalization, lost mirror ACK, later actual
END/reopen, responsive GUI and YES/NO completion without physical END.

Old auto-END expectations were replaced with stronger immutable START identity,
timestamp, raw-event/no-new-END and history checks in shift_end_release/actions,
network_resilience, windows_user_handoff, windows_handoff_module/replay_order and
simulated_shared_host_shortcuts tests. Existing real END identity/time replay
checks remain. No assertions were marked expected failures or skipped.

First local full run: **59/60 scripts PASS, one FAIL** in ui_recovery_timing.
Its fixture held the removed implicit Windows handoff lock. It now holds the
actual central position-recovery lock, keeping the 13-second hold, >12-second
elapsed assertion, >100 GUI heartbeats, 31-second ceiling and receipt checks.
Targeted repeat: **PASS**, 18.074 seconds recovery and 361 heartbeats. This is
documented adaptation to the approved removal of implicit END, not an increased
timeout or weakened integrity check. Final full platform run: **NOT RUN yet**.

Next exact step: push the D1 commits and inspect the single Windows/Linux source
workflow. It runs D1 targeted tests first, then all previous START/END/handover
gates and the complete suite. Diagnose failures without weakening checks. Save
exact tested source SHA, run/job IDs and PASS/FAIL here, then **STOP after D1**.
Do not begin D2 or build an EXE. Main, CURRENT_APPROVED.json, approved EXE,
service shortcuts and real data remain untouched.

---

# Previous Phase C checkpoint — source PASS

## Phase C continuation from a9b8982 — source verification PASS

Branch `feature/central-only-simple-20261027`; clean starting HEAD was
`a9b898213eb543782114abd330bfe4ed96aeb6c5`, with approved merge-base
`4340c41865328cd893e6dc23fcdcedfefa7f9bf2`. Prior 56/56 platform gates were
accepted as evidence and their Windows diagnosis was not repeated.

Implemented exclusively confirmed booth replacement:

- Backend core commit `8efd285e53157d0cbcf437dc9f0692394557199d` adds
  `position_tracking_position_handover.py`. One BEGIN IMMEDIATE transaction
  validates the exact old START and new person's eligibility, inserts distinct
  END/START IDs with the identical full timestamp, changes the unique live claim,
  stores completed previous work and saves an immutable receipt with actor/reason.
- JSON event files are recoverable mirrors for this transaction. The immutable
  central receipt supplies both events and live/history state if mirror writes
  fail. Recovery is bounded and never re-applies an old live claim.
- Service returns HANDOVER_REQUIRED with the observed old START/name. GUI asks
  YES/NO, defaults NO, displays booth and directions, and submits YES with the
  exact observed START ID. NO makes no business-state write. A prior actual END
  follows the ordinary START path without a replacement question.
- Recheck retains the same operation identity after unknown ACK. Stale YES,
  duplicate commands and late writers cannot replace newer occupants.
- Existing event projections pre-index STARTs so same-second handover chains
  retain all completed work. Active-map reads use one SQL claim snapshot so a
  replacement between reads cannot hide both people. These are Phase C history/
  consistency integrations, not new historical-report or officer functions.

Service/GUI source commit: `3101a57dac951546c0f4f70f6c5509b8cdeabde7`.
Source CI: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40660029478
Linux job `122720454755`: PASS, focused gates and full 58-script suite.
Windows job `122720454349`: focused gates PASS; full suite 57/58 PASS, one FAIL:
`runtime_diagnostics_regression.py::test_rotation_is_bounded_and_records_remain_valid_after_writer_closes`
recorded 22/30 required real resource probes within its unchanged 5-second bound.
Its tight QTest.qWait loop can starve the Python diagnostics writer on Windows.
The fixture now pumps Qt and explicitly yields the Python GIL, with unchanged
deadlines, real resource probes, minimum count and file/record assertions.
Local diagnostics 5/5 PASS in 1.464 seconds; repeat platform gates now PASS below.
Failure evidence: `docs/validation/central-only-20261028/phase-c-3101a57.json`.
EXE workflow `40660029897`: SKIPPED intentionally.

Latest verified source/test commit: `e325229b5547346caff027d9fb3f3f10eb97e948`.
Repeat source run: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40697620744
Linux job `122848497381`: focused gates and full 58/58 scripts PASS.
Windows job `122848496917`: focused gates and full 58/58 scripts PASS.
The run is completed SUCCESS. Both platforms passed handover backend 16/16,
handover Qt GUI 5/5, stale-worker 6/6, END 4/4, recovery 25/25, service 11/11 and
existing operator GUI 6/6 in the focused step, followed by the full 58-script
suite with zero failures. Windows diagnostics regression also PASS.
Final exact job-log evidence:
`docs/validation/central-only-20261028/phase-c-e325229.json`.
EXE workflow `40697620977`: SKIPPED intentionally. Application source is still
`3101a57dac951546c0f4f70f6c5509b8cdeabde7`; the repeat changes only the test pump.

Local targeted evidence: backend 16/16 PASS; real Qt confirmation/recheck 5/5
PASS; existing recovery 25/25, END 4/4, stale-worker 6/6, service 11/11 and module
architecture 4/4 PASS. Network resilience and legacy identity checks PASS.
The final local full suite also passed 58/58 after the active-snapshot
hardening. Final repeated Windows/Linux source CI is PASS. No timeout or prior
safety assertion was weakened.

New tests cover: NO leaves canonical tables/raw events byte-for-byte unchanged;
ordinary START after actual END; YES timestamps/audit/history; same-ID retries;
identity collision; 15 concurrent clients; rollback between END and START;
process death inside SQL and after commit; lost commit ACK plus unavailable
read-back; projection outage/recovery; delayed pre-commit and post-commit workers;
same-second chains; coherent readers during and across the atomic transaction.

Changed source modules/functions:

- `src/position_tracking_position_handover.py`: `handover`, `_commit_handover`,
  immutable receipt validation and bounded mirror recovery.
- `src/position_tracking_store.py`: composes the handover capability.
- `src/position_tracking_position_recovery.py`: initializes handover schema and
  recovers/validates canonical receipt evidence.
- `src/position_tracking_positions.py`: `active_all` reads one coherent SQL
  claim snapshot while retaining legacy corruption checks and workstation labels.
- `src/position_tracking_event_queries.py`: merges canonical handover events and
  pairs same-second sessions using pre-indexed START identities.
- `src/position_tracking_central.py`: immutable confirmation identity and
  `CentralOperator.execute/check` handover/preflight/idempotency routing.
- `src/position_tracking_ui_central.py`: default-NO confirmation and `_poll`
  integration; existing single-flight action/recheck worker owns the request.

New tests: `tests/central_handover_regression.py` and
`tests/central_handover_ui_regression.py`. Source workflow
`.github/workflows/central-only-gates.yml` runs both first on Windows/Linux.
`tests/runtime_diagnostics_regression.py` only fixes its event pump as explained
above; no diagnostics application behavior, timeout or safety check changed.

Status: Phase C SOURCE VERIFICATION PASS; source-only candidate. No open source
failure or demonstrated data-integrity defect remains in the exercised scenarios.
Physical SMB interruption/restart, packaged EXE and 15 physical stations are
NOT RUN. No new EXE build, main/manifest/release, real service data,
shortcuts or deployed queues were changed. No officer or historical-entry feature
was started. Preview remains opt-in (`--central-only`).

Next step: preserve this verified candidate and perform Phase C acceptance on
an isolated real SMB test share with synthetic personnel before any packaged or
production acceptance. That environment is not available in this workspace.
The complete application/Issue #10 is still unfinished. Do not proceed to
officer/report features in this assignment. Do not repeat the completed source
diagnosis or build an EXE on the strength of these source gates alone.

Exact resume command (from the repository root):

```bash
git switch feature/central-only-simple-20261027 && git status --short --branch && git rev-parse HEAD && git merge-base --is-ancestor e325229b5547346caff027d9fb3f3f10eb97e948 HEAD && sed -n '1,155p' docs/ISSUE_10_STALE_WORKER_STOP_20261027.md
```

Continue from the commit containing this final documentation checkpoint (its
exact SHA is returned by the command and final handoff). Its only changes after
the CI-tested e325229 source/test revision are this checkpoint and log evidence.

---

# Previous Windows/Linux source gates PASS, 28 October 2026

## Current continuation from 81ccc3a (supersedes the WIP below)

Application remains incomplete; no EXE or production change. Application source
is still `184567e3f0ef34cee11ce40b5728ea26fdbaa87a`. This continuation changes
regression fixtures and documentation only. The three original Windows failures
are resolved. Overall source verification at test revision
`e688cc79b9bb0f2df6a4ca0cbb5b270d985420a9` is PASS on both platforms:

- Diagnostic commit `8f9b95536df453f8b5608ff45dd76af9f37e88be`, run
  `40654847842`, Windows job `122703285275`, reproduces the three failures with
  worker state. START was centrally CONFIRMED, action future finished, and the
  read either was still in SQLite or already held the correct active START.
  GUI state was still dirty. There was no central write rejection or data loss.
- Fix `902c4ca3b9e093674322faec5965c7b6d637f34a` yields the Python GIL explicitly
  with `time.sleep(0.005)` between `processEvents` calls. The Windows tight
  `QTest.qWait(5)` loop starved the Python/SQLite worker compared with the real
  QApplication event loop. No application code, predicate, state assertion or
  5-second deadline was changed. Failure diagnostics remain for future evidence.
- Local PySide6 6.12: all 6 UI cases PASS in 4.801 seconds, normal process exit.
- Run `40655231061`, exact test revision `902c4ca`: focused stale-worker 6/6,
  END 4/4, recovery 25/25, service 11/11 and GUI 6/6 PASS on both platforms.
- Linux job `122704530746`: full source CI PASS.
- Windows job `122704530486`: full source CI completed with 54/56 scripts PASS.
  Failures were legacy `exit_responsiveness_regression.py` and
  `ui_workflow_regression.py`, which also pumped Qt using tight qWait loops.
  Their assertions/deadlines were retained; revision
  `e688cc79b9bb0f2df6a4ca0cbb5b270d985420a9` explicitly yields the GIL in those
  loops too. The offline code itself was not changed or revived.
- Local targeted validation of e688cc7: legacy exit 6/6 PASS (4.536 seconds),
  legacy workflow 1/1 PASS (4.105 seconds, 62 GUI heartbeats during recovery).
- Final verification run `40656531869` for e688cc7 is **SUCCESS** on both
  platforms: Linux job `122708794143` and Windows job `122708794596`.
  Each passed all focused gates and the complete **56-script suite, 0 failures**.
  This includes the three originally failing Windows GUI cases and the two
  subsequently exposed legacy regression scripts. Actual job-log summaries are
  retained in `docs/validation/central-only-20261028/source-gates-e688cc7.json`.
- EXE build run `40655231033`: SKIPPED intentionally. Packaged EXE, physical SMB
  interruption/restart and 15 physical stations: NOT RUN.

Exact next continuation instruction (do not repeat this completed diagnosis):

> Continue TDE-potition_tracking on feature/central-only-simple-20261027 from
> the commit containing this checkpoint. Verify clean HEAD and ancestry from
> e688cc79b9bb0f2df6a4ca0cbb5b270d985420a9 and approved baseline 4340c41865328cd893e6dc23fcdcedfefa7f9bf2.
> Read this current section first. Run 40656531869 already passed both complete
> platform gates. Continue Issue #10 with the next small Phase C change:
> explicit confirmed booth handover, atomic END-old + START-new with identical
> timestamp, preserved operation identities, actor/reason audit and stale-worker
> fencing. NO must leave all central state unchanged; ordinary START after END
> must show no handover dialog. Preserve all previous gates, use synthetic
> temporary stores, checkpoint and repeat relevant source CI. Do not modify main,
> CURRENT_APPROVED.json, approved EXE, production data or deployed queues.

Remaining Issue #10 work is NOT IMPLEMENTED/NOT VERIFIED by this checkpoint:
handover; officer authorization/panel and centralized roster administration;
full shift/live-position separation; historical report admissions, overlap checks
and regeneration; remaining officer/map/report GUI I/O isolation; eventual default
central-only entry and packaged candidate/real SMB acceptance. The operator
preview remains opt-in (`--central-only`), and passing source gates is not full
application completion or permission to use production data.

---

# Previous WIP CHECKPOINT, 28 October 2026

**STOPPED AT USER REQUEST / APPLICATION NOT COMPLETE / WINDOWS GATE FAIL.**
No programming, new tests, builds or further feature work was started for this
checkpoint. The sections below the historical divider retain earlier evidence;
this section is the current state.

## Latest saved source and branch

- Branch: `feature/central-only-simple-20261027`, repository
  `danilidish-coder/TDE-potition_tracking`.
- Latest source commit: **`184567e3f0ef34cee11ce40b5728ea26fdbaa87a`**.
- Preceding fixes: `25fd91902cbf54c5afa58ff8f3b9367fb57aa6ff`
  (transactional claims/fencing) and
  `fe144b3ee727595e4af3a2a2151a007d93483d9f` (Qt shutdown).
- Approved baseline remains ancestor
  `4340c41865328cd893e6dc23fcdcedfefa7f9bf2`.
- All application changes were already committed at source SHA above. The WIP
  commit containing this section preserves the handoff documentation only; its
  exact SHA is reported after push and can be read with
  `git log -1 --format=%H -- docs/ISSUE_10_STALE_WORKER_STOP_20261027.md`.

## Implemented since the previous STOP

1. Added `position_tracking_position_claims.py`: central SQLite live claims,
   unique physical booth/AGMS constraints, and per-attempt tokens. Conditional
   commits/aborts prevent a superseded worker from borrowing a retry's token,
   regaining authority or rolling back a committed operation.
2. Active position queries use the central accepted claim, rather than treating
   an overwritten/deleted JSON projection as authoritative. Superseded raw bytes
   remain available as evidence, marked ABORTED and excluded from work reports.
   Original operation IDs/times remain stable across retries.
3. Recovery revalidates the original END time against the effective START,
   including old aborted bytes delivered after a subsequent START correction.
4. Removed QWidget-bound work from the read worker. Shutdown stops new work and
   destroys native widgets on the GUI thread while QApplication still exists.
   Qt test fixtures use that same explicit deferred deletion. The subprocess
   check now covers repeated exits and exit with a blocked share read.
5. The original two stale-worker test methods and their assertions are unchanged
   from `340eeb3` (AST comparison verified). Four additional fencing cases and
   one additional END-time recovery case were added; no timeout was extended.

## PASS / FAIL / NOT RUN at source 184567e

CI run: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40570239152

| Check | Result |
| --- | --- |
| Original stale-worker assertions, plus four new cases | PASS, 6/6 in Linux and Windows focused gates |
| Original END interruption gate | PASS, 4/4 in both focused gates |
| Central recovery | PASS, 25/25 in both focused gates |
| Central service/worker | PASS, 11/11 in both focused gates |
| Local Qt 6.12 UI checks | PASS, 6/6, process exit 0 |
| Local portable runner | PASS, 56 scripts, zero failures in the completed previous execution |
| Linux CI job `122422193134` | PASS, including focused and full source regressions |
| Windows CI job `122422192745` | FAIL in focused Qt UI checks, 3/6 cases failing |
| Full Windows regression step | NOT RUN: preceding focused step failed |
| Windows EXE build, run `40570238840` | SKIPPED intentionally, not a build PASS |
| Packaged EXE, real SMB interruption/restart, physical 15-terminal acceptance | NOT RUN |

The local runner output was observed before this checkpoint, not rerun now.
Its temporary JSON under `/tmp` is no longer present in the current environment;
the CI run/job identities above provide the remote evidence. No new test run
was launched to recreate temporary files.

## Remaining failures / exact next task

Windows UI failures in job `122422192745`:

- `test_blocked_write_is_still_owned_after_ui_timeout`
- `test_exit_and_windows_account_change_preserve_central_active_position`
- `test_real_central_start_end_from_buttons`

All fail waiting for `end_btn.isEnabled()` with **"Qt state did not settle"**.
The cause is NOT YET DIAGNOSED. Do not assume this is merely slow Windows and do
not extend timeouts or weaken assertions. The former subprocess shutdown-crash
case passes in this run; the overall Windows gate still fails. Further Issue #10
feature development remains paused until the Windows gate is genuinely green.

Exact continuation instruction:

> Stay on feature/central-only-simple-20261027 in TDE-potition_tracking. Read
> docs/ISSUE_10_STALE_WORKER_STOP_20261027.md first and verify source ancestry from
> 184567e3f0ef34cee11ce40b5728ea26fdbaa87a and approved baseline 4340c41865328cd893e6dc23fcdcedfefa7f9bf2.
> Diagnose the three Windows Qt-state failures using run 40570239152, job
> 122422192745. Inspect actual worker outcomes, central claims and UI polling;
> do not increase timeouts or weaken tests. Make minimal fixes and repeat the
> focused gates and Windows/Linux regressions. Only after both platforms pass
> continue Issue #10. Do not merge main, modify CURRENT_APPROVED.json, build or
> replace the approved EXE, or access production data/queues.

No main, approved manifest, release EXE, production data, shortcuts or deployed
queues were changed. The candidate remains source-only and incomplete. No work
was discarded. Commit/push this checkpoint and verify its exact remote SHA.

---

# Historical STOP after stale-worker integrity proof

**HISTORICAL FAIL / NOT READY.** This earlier checkpoint superseded the
readiness conclusions in the earlier recovery and preview notes, while retaining
their actual, scoped PASS evidence. No assertion was suppressed or relaxed.

## Identity and completed work

- Baseline: `4340c41865328cd893e6dc23fcdcedfefa7f9bf2`.
- User-requested starting checkpoint: `839c3c5d319fdb5a1f0f2fa1526db78a870b58a8`.
- Branch throughout: `feature/central-only-simple-20261027`.
- Recovery source commit: `2599257440a9e8b46b770f1ef4ef21a092b44e42`.
- Direct-central preview source commit: `f0b4606ff51fa7bc083b12106d1e7ad56fcf9d71`.
- The stop checkpoint adds only failing safety tests, test-gate ordering and
  evidence/documentation. Application source remains that of `f0b4606`.

The original END receipt-gap defect now passes all four unchanged original tests.
Central evidence recovers its END/history on reopen and rejects a second END
under ordinary lock ownership. Cross-day IDs and corresponding ordinary START
interruption/reopen cases also pass. These fixes are retained for review, but
do not establish complete SMB safety.

## Newly reproduced failures

Command: `python tests/central_stale_worker_regression.py`.

The fixture uses real store code, OS/SQLite locks for new clients, a temporary
synthetic store and one blocked old worker. Only the old instance's officer-lock
contexts are replaced to model the SMB server releasing its locks while the old
call stack remains blocked. This is an explicit server-lock-loss **model**, not
a claim that physical SMB interruption was tested.

1. **FAIL — stale START:** old client records PREPARED and pauses before raw
   START JSON. A new client recovers, treats missing evidence as aborted, and
   starts another person at booth 1. Resuming the old call writes its JSON and
   active marker. Both people are now returned by `active_all()` at booth 1:
   `AssertionError: 2 != 1`.
2. **FAIL — stale END:** old client commits END JSON and pauses before the
   pending receipt. A new client recovers END and writes a new START for the
   same AGMS at booth 2. Resuming the old call writes the old receipt and
   unconditionally unlinks that AGMS's active path, removing the newer confirmed
   START. Reopen still returns None:
   `AssertionError: unexpectedly None`.

These are distinct from process death: a terminated process cannot resume;
an SMB-disconnected worker may still resume file operations through new handles.
Successfully acquiring a server lock is not proof that the previous call stack
has stopped. Bounded GUI workers and stable IDs alone do not fence that writer.

## Stop reason and required next design

Issue #10 follow-up comment `6450736281` explicitly says:
**"If integrity remains uncertain, STOP again with proof."** The two assertions
above are the proof. The Phase B preview is frozen and no Phase C/D or packaging
work follows. Its flag remains opt-in for source review; do not run it against
production or treat its existence as acceptance.

The next repair needs centrally enforced fencing/conditional state transitions,
not just another timeout or an extra unvalidated lock acquisition. In particular:

- A superseded PREPARED operation must never regain authority when an old worker
  resumes. A missing raw file cannot by itself prove that its worker stopped.
- No END projection may remove a newer START. Both the canonical live claim and
  its projections must validate the exact immutable START being changed.
- Booth/AGMS exclusivity must remain centrally enforceable after server lock
  loss. Stale JSON projections must not become authoritative live/report state.
- Preserve original events/IDs/times and audit; do not repair real deployed data
  or delete queues during this work. Keep the new failing gates unchanged and
  run them before further operator/officer work.

## Test ledger

| Evidence | Result |
| --- | --- |
| Original END gate | PASS, 4/4 unchanged |
| Ordinary central recovery suite | PASS, 24/24 |
| Direct-central service/worker | PASS, 11/11 |
| Local Qt preview, PySide6 6.8.3 | PASS, 6/6 |
| Local portable scripts before adding stale-worker gate | PASS, 55 scripts |
| New stale-worker safety model | **FAIL, 2/2** |
| Overall integrity/readiness | **FAIL** |
| Packaged EXE, real SMB, 15 physical stations | NOT RUN |

The full local runner's earlier 55/55 result is not a current all-green suite:
it did not yet include the two new assertions. The new test is discovered by
the normal full runner and is now the first focused source-CI gate. No expected
failure markers, assertion changes or timeout increases were used.

## CI evidence for source f0b4606

Source run: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40566794748

Linux job `122410105225`: **FAIL** in focused operator UI checks. END 4/4,
recovery 24/24 and service 11/11 passed first. UI subprocess exited `-6` under
PySide6 6.12.0 / Ubuntu 26.04; first diagnostic:

```text
QObject: shared QObject was deleted directly. The program is malformed and may crash.
corrupted double-linked list
```

The failing test was
`test_central_preview_launch_never_initializes_legacy_window_or_local_providers`.
Full CI source regressions were NOT RUN because that focused step failed. Local
PySide6 6.8.3 success is not used to override this crash. The shutdown ownership
problem also needs diagnosis before the preview can be accepted.

Windows job `122410104556`: **FAIL** at the same UI subprocess assertion, exit
code `3221226505` (hex `0xC0000409`). Its END 4/4, recovery 24/24 and service
11/11 gates passed first. Full Windows source regressions were NOT RUN after
that focused failure. This is Windows **source** execution, not a packaged EXE
or physical SMB test. Both platform jobs in run `40566794748` failed; neither
is a candidate acceptance result.

The old EXE workflow run `40566794588` was **SKIPPED**, as intended for this
source-only branch. No candidate or production EXE was built, installed or
published. Main, CURRENT_APPROVED.json, approved binary, production data, queues
and shortcuts remain untouched. There is no new binary SHA/size/URL to report.

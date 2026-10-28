# Issue #10 — Windows GUI diagnosis, 28 October 2026

## Current continuation from 81ccc3a (supersedes the WIP below)

Application remains incomplete; no EXE or production change. Application source
is still `184567e3f0ef34cee11ce40b5728ea26fdbaa87a`. This continuation changes
only `tests/central_operator_ui_regression.py`:

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
- Windows job `122704530486`: full source CI IN PROGRESS at this documentation
  update. It is not yet marked PASS. Do not advance Issue #10 features before
  the full Windows result is known and any real failure is diagnosed.
- EXE build run `40655231033`: SKIPPED intentionally. Packaged EXE, physical SMB
  interruption/restart and 15 physical stations: NOT RUN.

Exact next step: read the final result/logs of run `40655231061`, Windows job
`122704530486`, without rerunning successful gates. If it fails, isolate the
first failing script and fix its actual cause without extending timeouts or
weakening assertions. Only after both full platform gates pass may the next
small Issue #10 change begin. Preserve branch
`feature/central-only-simple-20261027`, approved source ancestry and production.

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

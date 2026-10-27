# Issue #10 — STOP after stale-worker integrity proof

**OVERALL FAIL / NOT READY.** This is the current checkpoint. It supersedes the
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

# Issue #10 — central recovery checkpoint

Continues `839c3c5d319fdb5a1f0f2fa1526db78a870b58a8` on
`feature/central-only-simple-20261027`, descended from approved baseline
`4340c41865328cd893e6dc23fcdcedfefa7f9bf2`. Implements the follow-up instruction
in Issue #10 comment `6450736281`. Supersedes the Phase A END blocker only;
the complete central-only application is not yet delivered by this checkpoint.

## Change and commit boundary

Before an immutable central START/END JSON file is written, its ID, original
payload and exact relative file path are recorded in `position_operations` in
the existing **central** `shift_reports.sqlite3`. The JSON file remains the
commit evidence. A missing/unacknowledged active marker or pending-session
receipt no longer makes a committed event undiscoverable. Reopen and the next
mutation recover unsettled operations under one OS-held central transaction
lock, then the person lock. SQLite enforces one non-aborted END per START and
globally unique operation IDs. Read-back validates the original payload.

Recovery removes only the matching active marker, reconstructs completed history
with the original IDs/times/actor/reason, and never closes a replacement START.
START committed just before process death is likewise reconstructed and reserves
its physical booth. A completed START cannot be resurrected by a cross-day retry.
The previous definite pre-marker START failure compensation remains unchanged:
only that newly attempted, unconfirmed event is removed when marker absence is
confirmed; existing operational history is not deleted.

Indexing completed history can remain pending while the booth is already safely
released. This preserves the existing report-index outage behavior. It never
makes the END speculative: the immutable central event is still required.

Files changed:

- `src/position_tracking_position_recovery.py`: central index and recovery.
- `src/position_tracking_positions.py`: journal before event; ID-based lookup,
  mutation serialization, identity checks, preserved original retry times.
- `src/position_tracking_session_index.py`: central END evidence releases a booth
  even when the old pending-session receipt was never created.
- `src/position_tracking_store.py`: recovery on opening a central store.
- `src/position_tracking_store_io.py`: flush/fsync JSON before atomic rename.

## Bounds and compatibility

Only isolated candidate shares are supported for testing. **Do not point this
candidate at production data or run a legacy EXE concurrently against its store.**
The first candidate open imports existing raw event evidence once, capped at
20,000 filesystem entries. Later opens use the index and at most 256 unsettled
operations. Exceeding either bound, unreadable evidence, duplicate legacy ENDs
or contradictory STARTs blocks mutation; evidence is preserved. These are limits
on work/counts, not guarantees that an SMB system call cannot block. GUI worker
isolation is a separate Phase B task. No real shared data was scanned.

No local outbox, offline replay, Windows identity or user profile is needed by
the recovery module. Existing local queues were not read, migrated or changed.
No main/manifest/release/production EXE or shortcut was changed.

## Evidence (Linux, Python 3.12, synthetic temporary stores)

- **PASS** `python tests/central_end_interruption_regression.py`: original 4/4,
  including the two formerly failing assertions, unchanged.
- **PASS** `python tests/central_position_recovery_regression.py`: 24/24.
  Includes actual child-process death after START/END JSON commit, cross-midnight
  and cross-day retries, legacy evidence with no new index, preserved actor and
  reason, 15 simultaneous synthetic clients, stale END/replacement protection,
  corruption/conflict/size-limit fail-closed behavior, and original retry time
  checked against a subsequent audited START-time correction.
- **PASS** `python tests/start_marker_ack_regression.py`: 3/3, unchanged.
- **PASS** `python tests/network_resilience_regression.py`: 15 groups, 250 serial
  cycles and 56 concurrent claims, unchanged.
- **PASS** previous `personnel_history_sqlite_regression.py`,
  `shared_file_lock_concurrency_regression.py` and `module_boundaries_regression.py`.
- **PASS** full `tools/run_regressions.py`: 53 scripts, zero failing scripts
  before the final streamed legacy-scan and retry-time hardening. The focused
  recovery/network checks above were rerun after that hardening.
- **NOT RUN** Windows-only skipped cases, actual packaged Windows EXE, real SMB
  interruption/restart and 15 physical terminals. Linux file fault injection and
  process death do not establish Windows SMB field acceptance.

Qt dependencies for headless source checks were installed into
`/tmp/tde-issue10-deps`; tests needing Qt used
`PYTHONPATH=/tmp/tde-issue10-deps QT_QPA_PLATFORM=offscreen`.
No Windows build/Actions run or EXE hash is claimed for this source checkpoint.

## Next step

Begin Phase B with direct-central operator requests and bounded worker ownership.
Retain a request's immutable ID on uncertainty; never enqueue offline work or
interpret a GUI timeout as cancellation. Keep Phase C handover, officer/shift
separation and Phase D historical report work as separately tested changes.

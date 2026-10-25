# Codex task — SIMPLE CENTRAL-ONLY Position Tracking (25 October 2026)

## Mission
Build an intentionally simpler, more reliable Windows version of TDE Position Tracking. This task is approved as a development experiment ONLY. User explicitly prefers deleting nonessential features over a sophisticated system that locks up at a booth.

Starting point: approved v1.2.6 tag, commit eed6edab485c8ae5800c5b62f4c2cdfc29ee32e6. Work ONLY in feature/simple-central-only-20261025. Do NOT alter main, tag v1.2.6, release EXE, real shared data, installations, or other repositories. No deployment until explicit acceptance.

## Non-negotiable behavioral contract
1. Remove offline START/END queue and conflict workflow from the NEW application's runtime. NO local SQLite outbox writes or offline replay, NO persistent local conflicts or dependency on Windows-user handoff queue to let an officer perform START/END. Do not delete historical queues: they may contain unreported operational events.
2. On START/END, attempt central write with a unique stable idempotency token. A success is displayed ONLY after the central server confirms the actual durable operation. If connection fails or response is ambiguous, show **uncertain / check status** rather than falsely saying it failed and encouraging a duplicate. Query central state by the stable event ID before retry; never create duplicate START/END. A network outage must not freeze the UI.
3. On unreachable central share, show "ΧΩΡΙΣ ΣΥΝΔΕΣΗ — ΔΕΝ ΕΠΙΒΕΒΑΙΩΘΗΚΕ ΚΑΤΑΧΩΡΙΣΗ", block further writes until connectivity confirmed; allow safe read-only cached display with clearly stale timestamp ONLY if already available; do not claim new writes. Provide clear nontechnical recovery action. No background queue.
4. Preserve officer/position locking (one officer per position, one active position per officer), exact historical timestamps, audit trail, durable end-to-start relationships and existing reports. Must handle concurrent booth starts, same officer from different PCs, multiple Windows accounts per PC, delayed SMB ACK, process crash, and old data.
5. Never auto-close centrally active positions just because Windows user changed or a session was locked. If old behavior necessary, require explicit, auditable officer action.
6. Avoid GUI-thread synchronous SMB/file/SQLite operations on START/END and message dialog; asynchronous bounded workers plus meaningful timeouts, UI spinner/nonblocking progress and error states. Keep all significant state transitions predictable.
7. Keep UI simple and Greek-first: START, END, current occupations, readable messages/errors. Inventory existing features and propose dropping any not vital to booth operations. Preserve reporting/integrity until separately approved to remove specific functions.
8. Existing local queue must be checked in READ-ONLY mode during migration / readiness check. If pending or conflict records exist, require manual verified reconciliation with central records, NOT automatic deletion, rename, reset or silent ignore. Determine exact machine queue from machine_queue.py, including env override, not from assumptions.
9. Provide rollback to approved v1.2.6 and maintain a test-only EXE distinct from approved EXE. Production paths and real data are off limits.

## Implementation and verification
- Inspect source modules: position_tracking_ui_positions.py, position_tracking_offline.py, position_tracking_handoff.py, position_tracking_machine_queue.py, position_tracking_positions.py, position_tracking_communication.py, position_tracking_ui_messages.py, position_tracking_ui_communication.py, position_tracking_store.py, plus associated tests.
- Architecture decision first: minimize change surface and remove runtime dependency on local queue rather than rewriting all modules.
- Automated tests: central START/END, duplicate protection/idempotency, stale-state retry, network outage/disconnect during commit, two simultaneous clients same booth, multiple Windows accounts, clock and shift boundary, end-to-start history, failed database writes, message dialog responsiveness. Synthetic mock tests are not equivalent to SMB Windows field tests.
- Real Windows-built EXE and CI evidence for exact commit. Report test results honestly, with gaps.
- Read and respect repo DEVELOPMENT_RULES.md and matching Google Drive technical reports, especially reliability report; do not rerun tests blindly.
- Maintain clean self-contained implementation notes and migration plan; branch only, no merge or release without separate approval.

## Acceptance
A standard booth operator must never need to find/delete SQLite/JSON files, manage offline conflicts, or summon the AΞΥΠ to unstick a workstation. With valid network central operations either succeed and are confirmed or yield a precise, recoverable nonfatal state. No data loss or false success.

# Exact reliability checkpoint — 2026-10-16

Task explicitly resumed from 801f91db09b17e5cdf77a952f8c21326ce5513a7.
Only feature/v125-modularization-20261013; existing .venv reused. No production,
main, release/tag or operational-data changes. No new modularization is needed.

## Current code and completed work

Current source/test candidate: 1554dedb68afecc3c39fe6cfdeb275ad7263aa8e.
Application src tree: b64def01b4762ce123711e9eec0fe5debae1da5c.
This documentation commit is identifiable by git log -1 -- docs/CONTINUATION.md.

- 4ef0041: blocked personnel reads coalesced; 200 changes previously queued 199
  requests. One active read/current selection now; full local 46 scripts PASS.
- 39b44f0: delayed GUI observation cannot resurrect an ended START or erase a
  newer START after another journal process advanced state. Atomic local revision
  comparison, no network-spanning SQLite transaction; full local 46 PASS.
- 1589663: local/remote confirmed exit off Qt, single exit worker, original START
  identity guards, no false ACK/quit with failure/pending data; cleanup has no
  shared I/O. Five targeted cases and full local 47 scripts PASS.
- 5231b30: bounded local runtime watchdog/resource samples and real Qt soak tool.
  Logs under local_root/diagnostics; no personnel/text/locals/full paths.
- 1554ded: deterministic post-close diagnostic test observer; no app source change.
  Final local 48 scripts PASS, targeted diagnostic suite 5/5 repeats PASS,
  compileall src/tests/tools and diff checks PASS.

## Exact CI status for 1554ded

- Linux 38905426334 SUCCESS (48 scripts).
- Modular gate 38905426542 SUCCESS.
- Windows 38905426410 IN PROGRESS at last checked status. New EXE acceptance,
  strict visual and artifact still pending. Do not claim overall Windows PASS.

## Measured soak

600.023 seconds PASS: 17 injected disconnect/recovery cycles; 34 original
operations, 17 sessions; 5 waves of 15 =75 separate simulated client processes.
29,823 Qt ticks; max gap 0.128s; UI process CPU 2.03% of one core; warm RSS
increase 2.195MiB, handles +1; observed queues network/state/position peak 2/1/1.
No GUI/worker stall events. Raw report/samples/logs preserved in
validation/reliability-20261016/soak-600s/.
Soak ran from 5231b30. Provenance verifies identical src tree and tool blob in
1554ded; no repeat needed for test/docs-only changes. Ten minutes is not 24h
or real SMB certification. All datasets synthetic and isolated.

## Failure history retained, not waived

5231b30 Linux 38904486037 and Windows 38904486330 FAILED in new test observer:
live file rotation read race (FileNotFoundError/PermissionError). Build/EXE/visual
did not execute. Gate 38904486493 SUCCESS. Full original CI logs committed.
First split-observer repair failed a full local run because fixed 400ms did not
ensure rotation; its 5 targeted passes were NOT treated as overall PASS.
1554ded waits for 30 actual probes then closes the writer before checking every
retained JSON record, actual rotation and unchanged bounds. No runtime change.

Earlier modularized source 762c3a36: Windows 38874685744, Linux 38874685771,
gate 38874685792, recovery 38874685760 (8/8) SUCCESS. Its accepted EXE hash/artifact
are in MODULARIZATION_REPORT_EL.md; do not confuse with the pending hardened EXE.

## First next action and remaining risks

Inspect existing Windows 38905426410; fetch/fast-forward newer diagnostic commits.
Verify regressions, frozen EXE functional provenance/IDs/timestamps, strict visual
0/20 startup, 0/30 theme, 30 clicks and actual accepted artifact/EXE SHA256.
If failed, diagnose preserved original error; no blind rerun or criteria changes.
If passed, update final source/artifact/hash in reports and this checkpoint.
Do not repeat completed modules or tests for unchanged code.

Read RELIABILITY_REPORT_EL.md and FIELD_ACCEPTANCE_EL.md. Remaining real tests:
15 PCs/SMB/ACL, actual Windows identities/session/logoff/reboot, power loss,
10:00 and 12/24h operation, printing/DPI/cache. Synchronous history/admin/map/
message/roster/shift I/O paths remain potential stalls requiring controlled field
fault reproduction and targeted follow-up. Python threads cannot forcibly bound
an OS SMB call; true process termination under hung I/O remains uncertified.
No unsafe thread kills or lost-queue shortcuts were added. Per-process diagnostic
rotation is bounded; cross-session retention policy still needed before long use.

Historical checkpoint text: validation/continuation-history-20261016.md.

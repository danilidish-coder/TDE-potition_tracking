# Current checkpoint: map END and offline idle exit — 2026-10-16

Idle-exit correction c7cdfd5: real empty/offline application can close without
inventing END or waiving pending/active/unknown journal state. 10 real-process
Qt cases and full 49-script suite PASS. Earlier accepted 1554ded has the reported
idle-exit bug; do not confuse old artifact with a new fixed candidate.

Next confirmed defects: map selected read blocked Qt for 0.800s; map END closed a
replacement START created during its confirmation. Both before failures retained
in validation/live-map-end-20261016/before.txt. Corrected selected-read and END/
audit I/O on the existing single map executor, exact expected START identity,
one-operation guard, no late END after closing a read, and no closing while END
awaits acknowledgement. Owner tracks pending map mutation; normal/remote app exit
drains it before confirming closure. Watchdog now samples that future's age.

5 map tests, 6 exit tests and full **50 portable scripts PASS**; no schema/event
ID/timestamp changes. Remaining map correction-time action still synchronous and
is not claimed fixed. No repeat of previous 600s soak (different earlier source).

Next: extend real frozen EXE driver with a separate empty-profile/no-roster/
no-central launch and actual native Exit confirmation/process termination;
require that evidence before artifact acceptance. Then one combined native
Windows/Linux/gate cycle for the completed candidate, with targeted local tool
checks first. Preserve all logs. No main/stable/release/operational-data changes.

Previous checkpoint below retained as history.

# Resumed: reported idle/offline exit — 2026-10-16

Starting checkpoint 278307b6ff46223db0685bcc867f9229b7e1554b; remote matched.
Home report reproduced in a real launch/QApplication loop/child process, without
central folder, roster or START/END. Original failure preserved in
validation/idle-exit-20261016/before.txt.

Fix: distinguish application closure from confirmed service END. Local idle exit
is permitted only for an explicitly tracked never-used window, with no initial
handoff error, settled relevant futures and a consistent local-journal proof:
no unresolved/unknown operations, no active/invalid observations, every START
matched by an applied END. Corrupt/unknown state fails closed. No schema or
ID/timestamp changes, no END/ACK/share access in local-idle branch. Remote CLOSE
still requires central confirmation/ACK; attempted START/END never uses shortcut.

10 targeted real-process Qt cases PASS, including no-central process termination,
confirmed closed history, pending/conflict, applied-unclosed START with empty
cache, observed active/corrupt state, in-flight work, attempted action and remote
command protection. Entire portable suite **49 scripts PASS**. Source compilation
and diff check follow before commit. Current native EXE acceptance is pending;
1554ded remains previous accepted binary and contains the reported idle-exit bug.

Next: targeted remaining GUI/SMB risk: live-map service mutations currently read
and write shared state on Qt and END does not guard the exact selected START.
Reproduce before changing, then minimal correction and focused/full local checks;
one final combined Windows/Linux/gate cycle only after the candidate is ready.
No repeats of completed modularization or earlier long soak. Remaining real field
acceptance in FIELD_ACCEPTANCE_EL.md and RELIABILITY_REPORT_EL.md.

Earlier checkpoint below is historical and superseded by this header.

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
- Windows 38905426410 SUCCESS: 48 scripts, build/smoke, frozen EXE workflow
  (4 operations, 2 sessions, original IDs/timestamps), strict visual 0/20 startup,
  0/30 theme, 30/30 confirmed clicks and accepted test EXE upload.
- Native evidence commit: 4e7b238115473049be065cce603003db2449baca.
- Artifact: POSITION_TRACKING_WINDOWS_TEST-1554dedb68afecc3c39fe6cfdeb275ad7263aa8e-38905426410.
- EXE SHA256: 0ba9f89e4fafde54ad5c53489af320178e4fc61ac4a28dca85f98367933db3d6.
- Artifact URL: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38905426410.
- Final exact metadata: validation/reliability-20261016/final-verification.json.
  Artifact retention 7 days; no release/tag or production deployment.

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
are in MODULARIZATION_REPORT_EL.md; superseded for current testing by the accepted hardened EXE above.

## First next action and remaining risks

All feasible checks in this implementation cycle completed. On resumption read
this checkpoint, the two reports below, remote HEAD and any newer Actions. Do not
repeat modularization or accepted tests for identical source. First outstanding
action: controlled isolated Windows/SMB field fault reproduction of the remaining
synchronous GUI I/O paths while collecting the new watchdog logs; then perform
targeted fixes only for demonstrated failures. Complete the real 15-client,
Windows-account and 12/24-hour acceptance protocol before production approval.
The automated passes do not certify kernel-I/O cancellation or field reliability.

Read RELIABILITY_REPORT_EL.md and FIELD_ACCEPTANCE_EL.md. Remaining real tests:
15 PCs/SMB/ACL, actual Windows identities/session/logoff/reboot, power loss,
10:00 and 12/24h operation, printing/DPI/cache. Synchronous history/admin/map/
message/roster/shift I/O paths remain potential stalls requiring controlled field
fault reproduction and targeted follow-up. Python threads cannot forcibly bound
an OS SMB call; true process termination under hung I/O remains uncertified.
No unsafe thread kills or lost-queue shortcuts were added. Per-process diagnostic
rotation is bounded; cross-session retention policy still needed before long use.

Historical checkpoint text: validation/continuation-history-20261016.md.

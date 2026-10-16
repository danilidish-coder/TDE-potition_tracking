## v1.2.6 publication in progress — 2026-10-16

Version-only successor of certified 410bf72fe197e6e7d9a4a1a299a135a716c71bf3.
Application, VERSION.txt, Windows PE metadata and package manifest now target v1.2.6.
Publication is gated on the newly built exact EXE and independent exact-source CI.
No PASS or new EXE hash claimed before completion. Existing releases remain intact.
Only the explicit release commit opts into additive pre-release creation;
no existing publish-release.yml execution, replacement or deletion.

# Exact accepted checkpoint — 2026-10-16

Only feature/v125-modularization-20261013. Started from 278307b6ff46223db0685bcc867f9229b7e1554b.
Existing environment reused. Main/stable v1.2.5/releases/operational data unchanged.

## Exact current source and acceptance

Source/test commit: 410bf72fe197e6e7d9a4a1a299a135a716c71bf3.
Application src tree: aef033e4f06b6e568f35822a5c2d168d1a6db139.
Native diagnostics commit: cc3451dcb9450716f2473b3feb5a55a4020d8ca6.
The final documentation checkpoint SHA is given by git log -1 -- docs/CONTINUATION.md.

- Windows 38916161811 SUCCESS: all 50 regression scripts, build/smoke, native idle
  application exit (normal process exit code 0, no roster/central/records), and
  original four-op/two-session frozen EXE workflow with original IDs/timestamps.
- Linux 38916162147 SUCCESS: 50 scripts; native-only cases not executed on Linux.
- Module gate 38916162111 SUCCESS (Windows/Linux contracts).
- Strict visual: startup 0/20, theme 0/30, confirmed clicks 30/30. Original criteria
  unchanged, original frames/reports retained. No skipped failed scenarios.
- Final local: 12 real-process idle cases, 8 map tests, 6 exit tests, all 50 scripts,
  compileall src/tests/tools and diff checks PASS.

## Accepted test EXE

Artifact: POSITION_TRACKING_WINDOWS_TEST-410bf72fe197e6e7d9a4a1a299a135a716c71bf3-38916161811.
URL: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38916161811
EXE SHA256: 3f896e307abfcbde477e201259e02f2e2cd683eafe18064b9ecea3a81a790f24
Archive SHA256 (different): ff3736fe28a824b5bfd9207412b18d9e49506662d5902594c2eeac7d0c2c29fd
Size: 60.6 MB. Retention 7 days. Availability verified on completed Actions
page; EXE checksum from native functional report/mandatory packaging gate.
No production release/tag/deployment. Native screenshots/reports:
validation/windows-visual-38916161811-1/; Linux results: validation/linux-38916162147-1/.
Exact metadata and commits: validation/idle-exit-20261016/final-verification.json,
commit-ledger.json. New artifact supersedes intermediate ec8eab7 and older 1554ded.

## Completed fixes — do not repeat

- c7cdfd5: home idle/offline/no-roster exit. Application closure without END only
  with explicit never-used position state, settled relevant futures, no handoff
  error and consistent local proof: no unresolved/unknown operations, no active/
  invalid observations, all STARTs matched with applied END by ID and AGMS.
  Never infer safety from absent roster/network. Corrupt/unknown state fails
  closed. Attempted activity and remote commands retain strict central path.
- 8eb31dc: map selection and END/audit off Qt; exact selected START guard; one
  operation, no late END after read-only close, pending write stays visible,
  app/remote exit drains tracked map write before confirmation/ACK.
- a784152: require actual frozen-EXE no-roster/no-central idle exit proof before
  packaging, alongside all existing data/visual/source/hash acceptance gates.
- ec8eab7: map time-correction read/write off Qt; selected START checked under
  original officer lock, preserving legacy four-argument API/raw START timestamp.
- 410bf72: if connection fails AFTER Exit was clicked, re-evaluate the SAME strict
  local proof once the worker settles. No bypass of running task/timeouts/pending
  START. Added actual delayed-failure positive/negative Qt subprocess cases.

Original reproductions and all local outcomes: validation/idle-exit-20261016/,
validation/idle-exit-late-20261016/, validation/live-map-end-20261016/,
validation/live-map-correction-20261016/. Intermediate ec8eab7 also passed native
Windows 38914933955/Linux 38914934027/gate 38914933969; subsequent real late-case
failure justified the final new native cycle. No blind reruns or criteria changes.
The prior 600s soak belongs to its historical source; not repeated or transferred
as current-source certification. Modularization complete; no reorganization needed.

## Real next work and limitations

First next action on resumption: read this checkpoint, RELIABILITY_REPORT_EL.md,
FIELD_ACCEPTANCE_EL.md, remote HEAD and newer Actions; do not repeat accepted
work for identical source. Next software target: reproduce and remove remaining
history/report GUI shared-I/O waits with focused faults, then messaging/ACK,
roster and shift/admin paths. These have NOT all been made asynchronous.

Python future/thread timeouts cannot cancel a permanent Windows SMB syscall;
true process termination under such I/O remains uncertified. A pending map write
keeps its dialog open while Qt pumps events; unknown outcome is not cancellation
or success. No unsafe force-kill, fake END/ACK or queue deletion was added.
SQLite GUI reads retain 2s busy timeout; long-run/per-session log retention and
read-dialog churn under actual SMB outage remain field risks to measure.

Real 15-PC SMB/ACL, Windows accounts/session/logoff/reboot, host power loss,
10:00 and 12/24h, cached cold startup, DPI/printing remain UNEXECUTED. All testing
used isolated synthetic data. No service installation or production approval.
History: validation/idle-exit-20261016/continuation-history.md and continuation-before-final.md.

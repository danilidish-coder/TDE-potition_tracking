# Current checkpoint — idle exit and live-map hardening, 2026-10-16

Branch feature/v125-modularization-20261013 ONLY. Resumed from
278307b6ff46223db0685bcc867f9229b7e1554b; remote matched, clean start.
Existing environment reused; main/v1.2.5/releases/real data unchanged.

## Completed small corrections

- c7cdfd5: real offline/no-roster/no-actions home exit reproduced and fixed.
  Local idle closure requires explicitly never-used position state, settled
  relevant futures, no handoff error and consistent local journal proof: no
  unresolved/unknown operations, no active/invalid observations, all STARTs
  matched to applied ENDs. Never infer safety from no roster/network. No END or
  remote ACK in the shortcut. Attempted actions and remote commands keep strict
  central confirmation. 10 real-process Qt cases; full local 49 scripts PASS.
- 8eb31dc: map selection and END/audit off Qt; exact selected START identity
  guards replacement records. One operation; no late mutation after closing a
  read; pending write cannot be abandoned through map close. Application exit
  drains owner-tracked mutation; watchdog samples its age. Full local 50 PASS.
- a784152: frozen EXE acceptance now also requires fresh no-roster/no-central
  native idle Exit/Yes and actual normal process termination without records.
  Packaging fails if that evidence is absent/failed or sessions !=2.
- Current candidate: map correction-time read/write also off Qt; optional
  expected_start_event_id validated under existing officer lock, preserving old
  four-argument API. Stale correction cannot alter replacement START or raw event
  timestamp. 8 map tests, 6 exit tests, 10 idle-process tests PASS; full local
  **50 scripts PASS**, compileall src/tests/tools and diff checks PASS.

Original FAILs plus all outcomes retained in validation/idle-exit-20261016/,
validation/live-map-end-20261016/ and validation/live-map-correction-20261016/.
No thresholds loosened, no failed test waived. No repeat of old modularization
or old 600-second soak; that soak certifies its historical source only.

## Next action

One combined Windows/Linux/module-gate cycle is requested by the candidate push.
Inspect its real run IDs/conclusions, preserve diagnostics, verify all 50 scripts,
new real frozen-EXE idle-exit proof AND existing four-op/two-session workflow,
strict visual (20 startups/30 toggles) and accepted EXE artifact/hash.
Do not claim native PASS until it actually completes. Previous accepted 1554ded
still contains the reported idle-exit defect; do not offer it as the fixed build.
Then replace pending statuses in this checkpoint and RELIABILITY_REPORT_EL.md.

## Remaining limits

No force-kills or fake ENDs. OS SMB calls cannot be cancelled by Python future
or thread timeout; true process exit under permanently hung I/O remains a risk.
Map writes keep the dialog open until a real result (GUI still pumps); unknown
outcome must not be interpreted as cancellation/success. Other remaining GUI
shared I/O includes history/reports, messaging/ACK, roster, shift/admin paths.
Use targeted fault reproduction and existing watchdog logs for follow-up.
Real 15-PC SMB/ACL, Windows account/session/logoff/reboot, power loss, 10:00,
12/24h, printing/DPI/cached launch remain UNEXECUTED; FIELD_ACCEPTANCE_EL.md.

Current full report: RELIABILITY_REPORT_EL.md.
Previous checkpoint history: validation/idle-exit-20261016/continuation-history.md.

# Final late-connection candidate checkpoint — 2026-10-16

Intermediate source ec8eab72e5c95f7b31add2b2b4208d30fb2493ee: Windows
38914933955 SUCCESS, Linux 38914934027 SUCCESS, gate 38914933969 SUCCESS.
Native report verifies actual empty-profile/no-central/no-roster EXE normal exit,
zero records, no central creation, plus the full four-op/two-session workflow.
Strict visual 0/20 startup, 0/30 theme, 30 clicks. Exact reports committed under
validation/windows-visual-38914933955-1/; previous accepted artifact is retained.

An additional controlled delayed-failure case proved a real gap after the exit
click. The final candidate re-evaluates the SAME strict local proof after the
connection worker settles; it does not ignore a timeout on running work, pending
START or any other protected state. 12 real-process idle cases and all 50 portable
scripts PASS, compileall/diff PASS. Original FAIL and final outcomes preserved in
validation/idle-exit-late-20261016/. Current app code changed, so final native
acceptance must refer to the new candidate SHA, not the intermediate PASS above.

Next action: inspect the one final combined Windows/Linux/gate cycle initiated
by this candidate push; require native idle exit, data integrity, strict visual
and actual accepted artifact/hash before delivery. Do not rerun tests blindly.
Other completed work, constraints and genuine remaining risks below remain valid.

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
  central confirmation. 12 real-process Qt cases; full local 49 scripts PASS.
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
  timestamp. 8 map tests, 6 exit tests, 12 idle-process tests PASS; full local
  **50 scripts PASS**, compileall src/tests/tools and diff checks PASS.

Original FAILs plus all outcomes retained in validation/idle-exit-20261016/,
validation/live-map-end-20261016/ and validation/live-map-correction-20261016/.
No thresholds loosened, no failed test waived. No repeat of old modularization
or old 600-second soak; that soak certifies its historical source only.

## Additional proven late-connection case

An exit clicked before the connection failure settled still errored despite an
empty journal. Reproduced in a real child process with a delayed failing worker.
After that worker finishes, re-evaluate the exact same local idle proof. A still
running worker, pending START, attempted activity, corrupt/active journal or remote
command remains blocked. No timeout or data guard changed. 12 targeted idle
cases and complete 50-script suite PASS. Evidence: validation/idle-exit-late-20261016/.
A new exact-commit native verification is required for this actual code correction;
inspect the already-running ec8eab7 native cycle before pushing the final candidate
so any driver problem can be diagnosed and combined, without blind reruns.

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

# Modular development — exact continuation checkpoint

## Scope and protection

Work only on `feature/v125-modularization-20261013`. Complete correctness fixes,
modularization, actual tests and a development Windows EXE autonomously. Make
small independently checked changes; do not waive failures or claim unexecuted
checks. Do not change main, production v1.2.5, real operational data or publish a
production release. Main was verified as
`3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`. Use the existing checkout and Python
3.12 `.venv`; no reinstall/worktree is needed. User explicitly permits independent
safe work while a separate problem is being diagnosed, without calling it passed.

## Current state and first pending action

This revision contains a locally validated candidate; it is NOT a completed
modularization or a production-ready build. First: push the unpublished commits
on this branch, await their exact Windows/Linux runs, fetch the diagnostic-only
CI commits, and inspect full reports. Never force-push over remote work.

- Atomic cache correctness commit: `ccbb271` (rebased before publication).
- Smoke bootloader-tree cleanup: `fcce6a4` (rebased before publication).
- This next commit adds physical pixel geometry, DPI-scaled clicks, a complete
  CI desktop, clipping rejection and preservation of partial visual reports.
- Full local suite after all candidate changes: **34 scripts PASS**. The native
  visual-process contract has 6 cases: 3 portable pass and 3 Windows-only cases
  explicitly skip on Linux. Real native cases must pass in Windows CI.
- Compileall src/tests/tools and git diff --check passed. No install was run.
- Source/app version, production EXE and release workflow were checked unchanged
  relative to original task base `129e8cb` (application logic changed only here
  on the isolated feature branch).

No current strict startup visual PASS has yet been established. The historical
last full workflow SUCCESS is source `9dbbb21`, Windows run `38800196045`, Linux
`38800195521`, module gate `38800195516`: 31 scripts on both platforms, EXE
build/smoke, 0/20 startup anomalies, 0/30 theme anomalies, 30/30 actual toggles.
Subsequent audit found startup-harness limitations, so that SUCCESS does NOT
certify 20 fresh/unclipped startups under the improved protocol.

## Verified fixes and evidence

1. `position_tracking_rendering.coherent_widget_update`: one top-level update
   transaction, polish/layout while disabled, synchronous whole-tree repaint.
   No processEvents, hiding, screenshots-as-overlays or threshold changes. Old
   `129e8cb` fails the real Qt paint-order contract; corrected app passes. Tests
   cover nested/disabled/exception states, queued-action non-reentry and 60 real
   application theme changes/persisted config in isolated directories.
2. `SharedEventStore.start` preserves durable START if active replace committed
   but its acknowledgement was lost, or marker/share state is unreadable. It
   removes the event only after confirmed absent marker/access to its directory,
   preserving the original before-write no-phantom behavior. Three store fault
   cases cover restart, same-ID retry, history and physical-booth exclusion.
   Commit `c81b91a` passed 32 scripts on both Linux `38801316804` and Windows
   `38801316650`; full Windows nevertheless FAILED its startup visual test.
3. Atomic cache candidate: conditional PENDING→APPLIED and observed-state update
   in one SQLite transaction. It also ignores a delayed already-applied replay
   so an old START cannot resurrect after a newer END. Three actual SQLite
   abort/concurrent replay cases fail on the old module and pass locally now.
   Windows validation of THIS change is still required.
4. CI failures diagnosed/fixed, not waived: Linux lacked libEGL.so.1 (CI now
   installs libegl1/libopengl0); captured Windows station subprocesses used cp1252
   (runner now explicitly uses UTF-8 throughout nested processes; Greek JSON
   round-trip contract added). Raw failed diagnostics remain under docs/validation.

## Startup visual investigation and current correction

User inspected original run 38794439758: toggle 24 had mixed light/dark rows.
After the rendering correction, three subsequent 30-toggle runs reported ZERO
endpoint theme anomalies, all clicks confirmed. Do not generalize this to every
field display or treat legacy pixel-change diagnostics as unintended flicker.

Run `38801316650` (c81b91a) still had 9/20 startup anomalies. Contact sheets
showed runner desktop/console before first UI and initial layout movement. Audit
found wait_for_window(pid) ignored PID and terminated only the onefile parent.

Fresh-process correction `fcc315e`, Windows `38803245321`, Linux `38803244931`,
module gate `38803244930`: all 33 portable scripts passed, including actual
Windows snapshot/taskkill contracts. Whole Windows run FAILED: 15/20 startup
anomalies, 0/30 theme anomalies, 30/30 clicks. Distinct root/child PIDs prove fresh
launches. Suspect windows had identical bbox before/after `[8,31,1036,751]`;
most differed only at t=0 and matched the endpoint by about 40ms. Contact sheets
show initial layout reflow, not mixed-theme colors. Do NOT ignore that first frame.

Current test-only correction uses per-monitor physical pixels consistently with
ImageGrab, scales clicks by GetDpiForWindow, REJECTS clipped client areas, and sets
CI desktop to 1920x1080. Smoke and visual cleanup kill the owned bootloader tree.
No frame, interval, endpoint threshold or failure criterion was removed. Partial
report.json plus exact errors are now saved in finally even on early capture or
window errors; a regression confirms the error still propagates.

Inspect actual new DPI/geometry/report data. If Set-DisplayResolution is unavailable,
diagnose its platform error; do not disable the clipping guard. A supported-display
CI test does NOT prove adaptive layout on undersized/high-DPI field desktops.

## Commands and access

From repository root:

```sh
XDG_CACHE_HOME=/tmp/tde-cache .venv/bin/python tools/run_regressions.py --out /tmp/tde-validation
.venv/bin/python -m compileall -q src tests tools
git diff --check
```

The runner executes every root tests/*.py separately except the mandatory desktop
EXE visual test (its own Windows step). Helpers live under tests/support. Do not
count a helper/zero-test script as validation. Exact results/logs go to --out.
Windows/Linux full suites and separate module gates run on feature pushes.

GitHub API and artifact download are blocked here; Git HTTPS read/push works.
Public github.com Actions pages expose status/job annotations. CI appends exact
results and failed .txt logs to docs/validation/linux-<run>-<attempt>, and reports/
thumbnail sheets/provenance to windows-visual-<run>-<attempt>. Full screenshots
remain in uniquely named Actions artifacts, one-day retention. Evidence writers
append only if tested source/configuration matches; docs-only parallel evidence
commits are preserved. Fetch and fast-forward or rebase only unpublished local
commits over those docs-only commits. Do not ask the user to retrieve files while
this supported Git evidence route can recover them. No credentials are logged.

## Remaining architecture work

Read ARCHITECTURE_AUDIT.md. Existing six original modules: common, Windows session,
machine queue, handoff, offline journal, bootstrap; rendering is the new isolated
Qt service. Main still contains configuration, personnel/roster, shared-store
services, reports and the nested UI. Full modularization remains UNFINISHED.

Next extraction after required gates: personnel/value records and OOXML/roster
import, with legacy exports retained. Four compatibility cases already passed
against old code in /tmp/tde_personnel_contract.py: Greek headers, leading-zero
IDs, duplicate merging, headerless known-ID roster, frozen records and invalid
files/read-only input. Move/adapt to repository tests, add direct module/facade
identity contract. The personnel module does not yet exist.

Then isolate settings/runtime paths; shared locks/communication, active positions,
shifts/history; report formats; Qt assets/theme/views/controllers; reduce entry
point to composition and compatibility exports. Use explicit dependencies with
no service importing the entry point. One coherent unit per change, full relevant
checks between units; no mechanical renaming of the monolith as completion.

Final development EXE must be uploaded as a test artifact after all required
checks and functional scenarios; no production release/tag update. Real multi-PC
SMB/ACL, host power loss, Windows lock/disconnect/logoff/reboot, 10:00 shift boundary,
long-running UI responsiveness, small/high-DPI displays, real printing and original
START/END identity/history checks remain field acceptance. Simulations do not
certify those. Update this checkpoint with exact SHAs/runs and the first pending
action after each stage. Do not claim full completion while these required
implementation/gate tasks remain.

## Independent personnel module candidate

The personnel/value/OOXML boundary is now implemented locally in
`src/position_tracking_personnel.py` with unchanged class bodies and legacy exports.
`tests/personnel_module_regression.py` has six passing contracts, including independent
import without the entry point or Qt. Full local suite after extraction: 35 scripts
PASS. No source/data format behavior was changed. This candidate needs its own Windows
build/portable/visual run before being considered fully verified.

The earlier physical-capture/atomic-cache revision `29b0a1f` has passed Linux (34 scripts)
and its module gate; Windows run 238 is still pending at this checkpoint. Preserve its
exact diagnostics, then rebase only this unpublished personnel commit over any docs-only
CI additions and push it for its own required checks. Do not describe pending Windows
checks as passed or the whole modularization as complete. Next independent unit after
these gates: pure theme palette/stylesheet data, then settings/runtime paths and the
remaining services/controllers listed in ARCHITECTURE_AUDIT.md.

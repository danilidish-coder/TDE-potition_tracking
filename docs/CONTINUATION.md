# Modular development — continuation checkpoint

Work only on `feature/v125-modularization-20261013`. Do not modify main,
production v1.2.5, real operational data, or publish a production release.
Use the existing checkout and installed Python 3.12 `.venv`; no reinstall or
worktree is needed. User's full instruction is to complete fixes, modularization,
tests and a development EXE autonomously, with small verified changes.

## Baseline and unresolved gate

- Remote baseline verified: `129e8cba8f9571c099bd46a11f6b979c741951b7`.
- Protected main: `3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`.
- Baseline: 29 local scripts PASS, module gate 38794439749 PASS.
- Full Windows 38794439758 failed its visual test. User examined its images:
  toggle 24 shows upper widgets already light, bottom buttons still dark;
  30/30 theme clicks activated. This is evidence of a mixed frame, not a reason
  to relax thresholds. Earlier 38788459409 also had 6/20 startup anomalies.
- Artifact 12001517568 was uploaded successfully (39.2 MB). GitHub API/artifact
  download is blocked in this cloud session. Public github.com Actions pages
  expose status and job annotations. Do not wait for artifact credentials when
  reported evidence and controlled repeats allow further diagnosis.
- Historical full Windows SUCCESS: b58b5b7, run 38787513005, but its theme test
  preceded the fix for false-green theme clicks. It does not certify the current
  visual criteria. No commit yet has verified full PASS under the new criteria.

## Candidate correction and reproducible checks

`position_tracking_rendering.coherent_widget_update` suppresses updates once at
the top-level window, finishes polish/layout and synchronously repaints the whole
widget tree when reenabling. No event-loop pumping, hiding, overlay or screenshot
mask. `_apply_theme` uses it instead of independently reenabling root/window and
only queuing `update()`. Production version and visual limits are unchanged.

`tests/rendering_regression.py` exercises synchronous paint of upper/lower widgets,
nested/disabled/exception states, no queued-action reentry, and 60 real application
theme changes with persisted configuration in temporary directories. The old
129e8cb application fails this paint-order contract; the candidate passes locally.
This demonstrates a scheduling difference, not yet Windows flicker elimination.

From repository root:

```sh
XDG_CACHE_HOME=/tmp/tde-cache .venv/bin/python tools/run_regressions.py --out /tmp/tde-validation
.venv/bin/python -m compileall -q src tests tools
git diff --check
```

The runner executes every portable test script separately and records exact exit
codes/logs. The Windows-only desktop EXE visual test is a separate mandatory CI
step. Full portable suites now run in Windows build and Linux push CI; module
gates remain separate. Visual artifacts upload even on failure, with one-day
retention. Inspect and record the exact commit/run results after pushing this
candidate. If Windows fails, diagnose and fix this step before further extraction.

## Remaining work after the gate

Read `ARCHITECTURE_AUDIT.md` for responsibility/dependency/coverage inventory.
Extract one coherent unit per change; preserve legacy entry-point exports and
data/path semantics. Suggested sequence: personnel/value models and OOXML import;
settings/runtime paths; store communication/locking, active positions, shifts and
history; reports; Qt assets/theme/views/controllers; reduce entry point to wiring.
Use explicit dependencies rather than importing the entry point from modules.
Run all portable checks and required Windows visual/build gates between changes.
Add meaningful contracts for newly isolated responsibilities, avoiding circular
imports and forwarding large modules under a new name without actual boundaries.

Keep this checkpoint current with exact SHAs, run IDs and first pending action.
Do not claim completion until full modularization, valid Windows/Linux checks and
development EXE functional scenarios succeed. Real multi-machine SMB/ACL/session
and extended field-use tests must be reported separately, not equated with local
simulations. Production publication remains a separate human approval.

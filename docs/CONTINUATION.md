# Continuation checkpoint — STOP, 2026-10-15

Development is paused by the user's explicit instruction. This checkpoint saves
completed work only. Do not start another module, diagnosis/fix cycle, CI run or
production release today. Resume only on the user's next instruction.

## Branch and exact commits

Use the existing checkout and existing Python 3.12 `.venv`; do not reinstall.
Work exclusively on `feature/v125-modularization-20261013`.

- Latest application source: `ec80b132c35c48f25a3b3601ad74a3290f769825`
  (pure theme module extraction, locally validated; native CI pending).
- Last Windows/Linux tested source: `22bc3bde7a69482fdac3d97fae5ab9538bfe1a81`
  (strict byte-identical prelaunch desktop classification).
- Personnel module: `1e7f2f20e6fa894a8db92b5dc38649397ebfd091`.
- Atomic offline replay/cache fix: `ccbb27132a510b7105282487ff3e053b769a8f2c`.
- Smoke process-tree cleanup: `fcce6a4d527f5290b5e605bd64c61d3aefb41c55`.
- START marker acknowledgement durability fix:
  `c81b91aa3fc7153ce5a2e1dd9893af05f5ef50a8`.
- Windows evidence commit: `43d92a9ad520bd4ef0a0145ea9c9dd9df9aaad6e`.
- Linux evidence commit: `0c588874d47903b2a52ff3ce46ed7fd4c4d6e8ff`.

The documentation checkpoint is the commit containing this file; obtain its exact
SHA with `git log -1 --format=%H -- docs/CONTINUATION.md`. It follows the source
commit above and is deliberately marked `[skip ci]` to save work without starting
a new verification cycle today. No force push is needed.

## Actual checks and failures

Latest source `ec80b132...`:

- Completed local suite: **36 scripts PASS**. Saved exact results and provenance:
  `docs/validation/local-theme-20261015/`. Three native Windows process cases skip
  on Linux; these skips are not Windows validation.
- Completed `compileall src tests tools` and `git diff --check`: PASS.
- Its own Windows build, smoke, visual test, Linux CI and module gate: **PENDING**.
  Do not transfer an earlier revision's results to this source.

Previous source `22bc3bde...`:

- Linux run **38806871712**: **35 scripts PASS**;
  `docs/validation/linux-38806871712-1/results.json`.
- Windows run **38806871707**: **35 scripts PASS**, EXE build and smoke PASS,
  but the complete workflow **FAILED** at `tests/visual_flicker_windows.py`:
  `RuntimeError: Visible flicker or unintended third-state frames detected.`
- Strict startup endpoint anomalies: **12/20**; recognized byte-identical initial
  desktop loading runs: **0**. Strict theme endpoint anomalies: **0/30**;
  actual theme clicks confirmed: **30/30**. Legacy pixel-change diagnostics are
  not the strict endpoint acceptance results.
- Full report, provenance, regression outcomes and diagnostic contact sheets:
  `docs/validation/windows-visual-38806871707-1/`.
  Run: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38806871707

The startup problem is **UNRESOLVED**. Earlier run 38805076037 on
`29b0a1fa538a69df32220af50c234a83708bd8cb` passed 34 portable scripts and
build/smoke but failed 15/20 startups. Inspected frames included desktop/console
before complete UI; this motivated capturing an actual prelaunch reference.
The latest exact-reference classifier did not recognize those frames as unchanged
desktop. Do not claim the remaining 12 anomalies are normal loading or confirmed
application repaint defects without inspecting their actual evidence.

Historical run 38800196045 reported all checks passing on
`9dbbb21fce2e9f9d938fca6659f01cdeeffecc62`, but subsequent harness audits found
PID/cleanup/viewport limitations. It does not certify the improved startup test.

## Completed implementation and module boundaries

- `position_tracking_rendering`: coherent top-level theme mutation, polish/layout
  and synchronous repaint, with paint-order, nesting, exception and real app tests.
- `position_tracking_personnel`: unchanged personnel records, read-only OOXML
  repository and roster import; legacy entry exports retained; six contracts.
- `position_tracking_theme`: unchanged theme dictionaries and stylesheet function;
  independent import, normalization and actual Qt pixel contracts (three cases).
- Existing modules retained: common, Windows session, machine queue, handoff,
  offline journal and bootstrap. See `docs/ARCHITECTURE_AUDIT.md` for boundaries.
- START history survives ambiguous committed marker acknowledgements; three
  fault/retry cases. Offline PENDING-to-APPLIED transition and observed cache now
  commit atomically; three SQLite abort/delayed replay cases.
- CI runs every root regression script, preserves exact failures, uses UTF-8,
  and retains Windows visual evidence even on failure. Native process ownership,
  tree cleanup, physical DPI geometry, clipping rejection and partial-report
  retention have explicit contracts.

No visual check was removed. Original application endpoint threshold remains
0.08. Only byte-identical initial prelaunch desktop frames may be launch latency;
partial/black/mixed UI, desktop returning after app pixels, zero frames and
only-desktop captures still fail. Raw frames/distances remain evidence.

## First action tomorrow and remaining work

1. Read this checkpoint and verify Git branch/HEAD against origin; no reinstall
   and no repeat of completed extractions. Inspect the saved failing startup
   sequences from run 38806871707, including reference versus first/worst/final
   images and geometry. Establish why exact desktop comparison recognized zero
   loading runs before selecting a correction; do not loosen criteria.
2. Verify the saved theme revision on its own native Windows/Linux CI and module
   gate. All three workflows support `workflow_dispatch`; select this feature
   branch. Do not dispatch today. GitHub API/artifact access was blocked in this
   environment, while Git HTTPS and public Actions pages worked. Use available
   authenticated workflow access tomorrow; do not claim a dispatch succeeded
   without a real run. The CI Git evidence transport can recover reports without
   asking the user to download them. Full screenshots are Actions artifacts with
   one-day retention; diagnostic thumbnails/reports are committed and persistent.
3. Fix only the evidenced cause in a small change, preserve failing evidence and
   require full PASS before continuing development. Full modularization remains
   incomplete: configuration/runtime paths, shared-store services/locks,
   shifts/history, reporting and Qt views/controllers remain in the entry module
   (approximately 4,837 lines after theme extraction). No next unit was begun.
4. Final development EXE download artifact is still pending (current EXE upload
   is disabled). No production release is authorized. Field SMB/ACL, host power
   loss, Windows session/reboot, shift boundary, extended UI responsiveness,
   small/high-DPI screens and real printing remain unverified acceptance work;
   temporary-directory simulations do not certify operational deployments.

For a later authorized verification cycle:

```sh
XDG_CACHE_HOME=/tmp/tde-cache .venv/bin/python tools/run_regressions.py --out /tmp/tde-validation
.venv/bin/python -m compileall -q src tests tools
git diff --check
```

CI may append diagnostics-only commits on this same branch. Fetch and preserve
them; rebase only unpublished local commits, never overwrite remote work.

## Protected state

Remote main remains `3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`.
`release/`, `VERSION.txt`, and the production release workflow are unchanged from
original task base `129e8cb`. No production v1.2.5 binary, tag, release or main
was changed; no real operational data was used or edited. All work is confined
to the development branch. Stop after publishing this checkpoint.

## Resumed 2026-10-16 — diagnostic-only checkpoint

User explicitly resumed development. Remote and local started at a323d9e878a7;
main is still unchanged. No newer remote diagnostics existed. Public Actions
confirmed 38806871743 module gate PASS, Linux 38806871712 PASS and Windows
38806871707 FAIL for 22bc3bd. API access still returns tunnel 403; Git works.

The next diagnostic-only revision leaves all src/ byte-identical to ec80b132c35c.
It adds per-frame desktop distance/difference bounding boxes and persistent original
failed-startup PNGs, with no acceptance change. Full local 36-script suite PASS
(/tmp/tde-diagnostic-20261016), compileall and diff check PASS. Push triggers the
three existing feature workflows, independently validating the saved theme source.
Await exact run IDs/results; no Windows PASS is claimed in advance.

Independent settings unit: `position_tracking_settings.py` plus compatibility
facade, six new contracts; 37 local scripts PASS, compileall/diff PASS. Exact logs
/tmp/tde-settings-20261016. Kept local while 0f6fee5 Windows evidence is pending;
Linux 38861912055 and module gate 38861912054 already PASS for 0f6fee5.

Pure report text/HTML boundary: 38 local scripts PASS, including five new
formatter contracts; /tmp/tde-report-text-20261016. No store/Qt/document dependency
at import; entry reexports retain object identity. No Windows PASS claimed yet.

PDF/history summary module: function ASTs exactly unchanged, legacy identities
retained; 39 scripts PASS (/tmp/tde-pdf-20261016), compileall/diff PASS. Independent
service import and missing-Qt failure contracts added; Windows still pending.

Word document/archive naming module: 39 local scripts PASS, including an actual
DOCX create/read round-trip; /tmp/tde-documents-20261016. Compileall/diff PASS.

Statistics workbook/charts module: 39 local scripts PASS, including existing
real workbook/archive regression; /tmp/tde-statistics-20261016. Compileall/diff
PASS. No report function behavior was changed.

Store I/O/locks/SQLite primitives: seven AST-identical methods extracted into
`position_tracking_store_io.py`, preserving BusyError identity via legacy export.
39 scripts PASS, including 72-way locks, marker acknowledgement and replay cases;
/tmp/tde-store-io-20261016. Compileall/diff PASS. Native CI pending.

Communication store boundary: 12 AST-identical heartbeat/message/ack/command
methods; 39 scripts PASS (/tmp/tde-communication-20261016), compileall/diff PASS.

Personnel history/session index: nine AST-identical reconciliation/search methods,
39 scripts PASS (/tmp/tde-session-index-20261016), compileall/diff PASS.

Shift schema/snapshot index: five AST-identical methods, 39 scripts PASS
(/tmp/tde-shift-index-20261016), compileall/diff PASS.

Windows diagnostic run 38861912057 FAILED on exact application src/ tree ec80b132:
36 portable scripts/build/smoke PASS, 14/20 startup anomalies and 1/30 theme
anomalies, 30/30 clicks. Linux 38861912055 and module gate 38861912054 PASS.
Original PNGs now retained in its diagnostics commit 09c8cf0. Pixel analysis of
startup_03: only 1043/835200 pixels differ from prelaunch desktop, on the bottom/
left console border (focus change). Startup_09/_10 are solid white real window
frames, not normal unchanged desktop. Neither has been waived. Next isolate the
CI background focus fixture, then correct actual first-paint/presentation and
retain originals for the failing theme toggle too. No threshold change allowed.

Stable visual background fixture: owned non-topmost STATIC/SS_GRAYRECT window
behind the application removes console-focus border changes from the experiment;
no captured application frames or criteria removed. White/black/partial UI still
fails. Original failing theme PNGs will also persist. 39 local scripts PASS,
with four native Windows process/fixture cases explicitly skipped on Linux;
/tmp/tde-background-fixture-20261016. Compileall/diff PASS, native fixture pending.

First-paint candidate: MainWindow sets Qt.WA_NoSystemBackground before building
widgets to avoid a separate native background erase before complete backing-store
content. No exposure delay, event pumping, screenshot overlay or test relaxation.
39 local scripts PASS (/tmp/tde-first-paint-20261016), compileall/diff PASS. This
is only a candidate until the next native startup/theme evidence demonstrates it.

START/END position service: ten AST-identical methods extracted. Initial full
suite failed ONLY the handoff test's requirement that its thin wrapper reside in
the entry file (StopIteration). Test now resolves the actual inherited method and
still asserts one return statement, identical standalone helper identity and all
real protected-ID/replay cases. Full rerun 39 scripts PASS
(/tmp/tde-positions-verified-20261016); initial failure retained at
/tmp/tde-positions-20261016. Compileall/diff PASS. No event logic changed.

Shift lifecycle/membership boundary: eleven AST-identical methods, including
pending/approved/excluded reversal and guarded END handling. 39 scripts PASS
(/tmp/tde-shifts-20261016), compileall/diff PASS.

Event/roster/shift query boundary: eight AST-identical methods, 39 scripts PASS
(/tmp/tde-event-queries-20261016), compileall/diff PASS.

SharedEventStore composition/maintenance now lives in position_tracking_store.py;
entry reexports the same class. Remaining class AST unchanged. Backend imports
without entry/Qt. 39 scripts PASS (/tmp/tde-store-composition-20261016),
compileall/diff PASS. The giant store has been replaced by responsibility modules.

Qt artwork/renderers extracted with unchanged AST/string values; 39 scripts PASS
(/tmp/tde-ui-assets-20261016), compileall/diff PASS. Windows f31fe5c run
38862995734 failed BEFORE build/visual in settings_module_regression.py; inspect
the retained .txt failure. Its visual hypothesis was NOT tested. Stop new UI
units until that actual Windows failure is corrected.

Windows settings failure is a test fixture path alias, not a persistence defect:
Path.resolve expands C:/Users/RUNNER~1 to C:/Users/runneradmin. Frozen-path expected
value now uses base.resolve(), preserving the original canonicalization contract.
39-script rerun PASS (/tmp/tde-settings-windows-path-20261016), compileall/diff PASS.

Development EXE packaging enabled ONLY on this feature branch after successful
build/smoke and complete strict visual results (20 startup, zero anomalies,
30 confirmed toggles). Package includes exact source SHA, EXE SHA256, regression
and visual reports; upload errors fail the workflow. No release/tag/archive update.
Three negative/positive package contracts, 40 local scripts PASS
(/tmp/tde-artifact-gate-20261016); compileall/diff PASS. Artifact is not available
until a real Windows run passes AND upload succeeds.

Live map Qt module: class ASTs unchanged. Initial full suite failed a UI source
string's quote/spacing assertion after equivalent AST rendering. The guard now
checks the same actual QPushButton constructors by AST, without dropping required
actions. Full 40-script rerun PASS (/tmp/tde-ui-map-verified-20261016); initial
failure /tmp/tde-ui-map-20261016. Compileall/diff PASS.

Main widget layout/theme controller: three AST-identical methods, 40 scripts PASS
(/tmp/tde-ui-view-20261016), including 60 real whole-window theme/persistence
changes. UI label guards follow the actual extracted class. Compileall/diff PASS.

UI configuration controller + explicit WindowServices providers: six methods,
with only app/local path calls redirected to the exact legacy-supplied callbacks.
40 scripts PASS (/tmp/tde-ui-configuration-20261016), including real config/theme
persistence under injected temporary paths; compileall/diff PASS.

UI heartbeat/alarm controller: five AST-identical methods, handoff guard now
inspects actual extracted heartbeat method. 40 scripts PASS
(/tmp/tde-ui-communication-20261016), compileall/diff PASS.

Message/remote-close dialogs: three AST-identical methods, 40 scripts PASS
(/tmp/tde-ui-messages-20261016), compileall/diff PASS. No messages were sent to
real users; backend communication tests remain isolated filesystem simulations.

UI personnel selection/active-state polling: six AST-identical methods,
40 scripts PASS (/tmp/tde-ui-selection-20261016), compileall/diff PASS.

UI position/offline controller: five methods, with only local-root lookup injected
through the same WindowServices callback. Handoff test inspects actual extracted
worker; 40 scripts PASS (/tmp/tde-ui-positions-20261016), compileall/diff PASS.

Native da9b4d1 run 38863724150: 40 regressions/build/smoke PASS, visual FAIL with
17/20 startup anomalies, zero theme anomalies, 30 clicks. No EXE artifact accepted.
WA_NoSystemBackground was ineffective: solid white startup frames remain. Owned
background needs its own Win32 message loop (currently unpumped while EXEs launch,
allowing stale/ghosted desktop pixels). Fix fixture separately. Then replace the
ineffective erase flag with a first-presentation readiness barrier: do not expose
an unpainted native surface; release after the complete initial Qt paint. Retain
all screenshot frames; no change to visual thresholds or theme transition checks.

Owned visual background now has a dedicated Win32 message thread, physical DPI
coordinates, checked foreground activation before EACH reference and deterministic
thread/window cleanup. This fixes the fixture's unpumped/ghosted-window defect;
40 local scripts PASS (/tmp/tde-background-message-loop-20261016), native cases
still pending. No screenshot frame or acceptance criterion removed.

Initial native presentation candidate replaces ineffective WA_NoSystemBackground.
Windows native surface is initially DWM-cloaked while its REAL Qt backing store
renders; a queued callback after root+descendant Paint delivery releases it once.
No snapshots/overlay, timed delay, processEvents or later theme hiding. Actual
Qt tests assert both top and bottom children painted BEFORE release, no re-cloak
on theme updates, refusal after show, and offscreen/non-Windows compatibility.
41 local scripts PASS (/tmp/tde-first-presentation-20261016), compileall/diff PASS.
Native verification remains mandatory; this does not certify the pending visual
issue. All captured desktop/application frames still use unchanged criteria.

UI safe-exit/lifecycle controller: four AST-identical methods, 41 scripts PASS
(/tmp/tde-ui-lifecycle-20261016), compileall/diff PASS.

Rendering prerequisite failure diagnosed, not bypassed: old test began theme
interaction from a 100ms timer scheduled inside QApplication construction. Failure
was reproduced at iteration=0, exposed=False, with ALL buttons missing paint.
The test now waits for the real initial root Paint (then queued exercise), has a
hard no-paint timeout and retains all 60 synchronous child-paint/persistence
assertions. Full 41-script suite PASS (/tmp/tde-render-readiness-20261016).
Initial failure logs: /tmp/tde-ui-shift-end-20261016; CI Linux 38865045885 and
Windows 38865045894 failed this same prerequisite before native build/visual.

Lightweight stage gate failure reproduced with python -S: UI method inspection
had imported PySide6 into the stdlib-only backend contract. It now parses the
actual controller methods by AST and asserts their bases are linked to MainWindow,
keeping all order/identity scenarios. python -S handoff replay contract PASS;
full 41-script suite PASS (/tmp/tde-lightweight-gate-20261016), compileall/diff PASS.

Resumed pending shift-completion modal after prerequisite test fixes. Method AST
unchanged, same single/bulk/finalize controls; 41 scripts PASS
(/tmp/tde-ui-shift-end-verified-20261016), compileall/diff PASS. Earlier failure
in this extraction cycle was the diagnosed pre-exposure test timer, not waived.

UI shift preview/membership/status controller: seven AST-identical effective
methods; removed the previously shadowed duplicate _shift_admin definition while
retaining its actual last definition. 41 scripts PASS (/tmp/tde-ui-shifts-20261016),
compileall/diff PASS. This does not change the guarded end dialog behavior.

UI report/archive dialogs: three methods, file-opening callback now explicitly
supplied by WindowServices with the same original behavior. 41 scripts PASS
(/tmp/tde-ui-reports-20261016), compileall/diff PASS.

Personnel history/statistics/PDF dialog extracted with unchanged method AST and
unchanged PIN/application constants now owned by position_tracking_constants.py.
Stage gate verifies the actual exported APP_VERSION value, rather than requiring
its literal assignment to remain in entry. 41 scripts PASS
(/tmp/tde-ui-history-20261016), compileall/diff PASS. No version/PIN value changed.

Officer admin/audit/backup/navigation controller: six AST-identical effective
methods, retaining last _live_map implementation and removing its dead shadowed
predecessor. 41 scripts PASS (/tmp/tde-ui-admin-20261016), compileall/diff PASS.

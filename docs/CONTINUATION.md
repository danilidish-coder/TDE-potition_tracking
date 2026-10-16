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

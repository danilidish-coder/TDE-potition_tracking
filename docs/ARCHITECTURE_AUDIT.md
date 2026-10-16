# Current architecture and verification map — 2026-10-16

Only feature/v125-modularization-20261013. Main and production v1.2.5 protected.
This is development verification, not field/production acceptance.

## Current structure

The completed modularization source 762c3a36 has 43 source files; entry 88 lines,
MainWindow composition 77, largest module 366. Reliability candidate 5231b30
has 44 files after adding the independent stdlib-only diagnostics utility;
intentional UI/offline corrections are documented in RELIABILITY_REPORT_EL.md.
The full per-file responsibility/line/commit inventory is in
MODULARIZATION_REPORT_EL.md and validation/structure-20261016/modules.json.
The original monolith inventory remains in Git history at checkpoint a323d9e.

| Responsibility | Current owners |
|---|---|
| Compatibility/launch composition | position_tracking.py, ui_application, ui_main, ui_context |
| Settings and paths | settings, machine_queue |
| Immutable personnel and roster import | personnel, common |
| Active START/END, corrections, idempotent receipts | positions, store_io |
| Shift membership/lifecycle | shifts |
| SQLite snapshots and history index | shift_index, session_index |
| Event projection and clock-window queries | event_queries |
| Shared clients/messages/commands | communication |
| Store composition, audit and backup | store |
| Durable replay and account transitions | offline, handoff, windows_session |
| Offline local Windows EXE bootstrap | bootstrap |
| Text/HTML, PDF, Word, Excel reporting | report_text, pdf, documents, statistics |
| Palette/style data and coherent repaint | theme, rendering |
| Qt view/assets/map | ui_view, ui_assets, ui_map, artwork |
| Qt business interaction controllers | ui_configuration, ui_selection, ui_positions, ui_shifts, ui_shift_end |
| Qt communication/admin/history/report dialogs | ui_communication, ui_messages, ui_admin, ui_history, ui_reports |
| Safe exit and initial presentation | ui_lifecycle, ui_presentation |

## Dependency and composition rules

Entry supplies explicit WindowServices config/path/file-opening callbacks. UI
capability mixins compose into the small MainWindow; store capability mixins
compose into SharedEventStore and share its explicit filesystem/SQLite state.
Services do not import the entry or UI. Reporting uses narrow session-source
contracts. Optional Qt/docx/openpyxl dependencies load only when needed by exports.
Legacy entry exports remain compatible. No import cycles or duplicate effective
business-method implementations. See tests/architecture_regression.py.

```mermaid
flowchart TD
    Entry["Entry: legacy API + runtime providers"] --> App["Qt application lifetime"]
    App --> Window["MainWindow composition"]
    Window --> Views["Views and UI controllers"]
    Views --> Store["SharedEventStore composition"]
    Views --> Reports["Report format adapters"]
    Views --> Offline["Durable outbox and handoff"]
    Store --> Capabilities["I/O, positions, shifts, indexes, queries, communication"]
    Reports --> Models["Personnel and common values"]
    Capabilities --> Models
    Offline --> Models
```

Historical modularization AST audit at 762c3a36: all 66 store methods unchanged versus 0f6fee5; all 50
effective UI methods unchanged after explicit path callback normalization.
Constructor composition is checked by real UI workflows. SQL/HTML string values
are compared using complete owning-module ASTs, without text dedentation.
Evidence: validation/structure-20261016/ast-audit.json.

## Resolved evidence and current certification

Initial capture contained console focus-border changes AND genuine unpainted
white native surfaces. CI background now owns a responsive message loop; initial
native presentation waits for actual completed Qt paint before uncloaking once.
Theme changes still use normal visible coherent repaint. No threshold change,
frame hiding/exclusion or screenshot overlay. See CONTINUATION.md for exact runs.

b943a869: full Windows 38865827943 SUCCESS, strict startup 0/20 and theme 0/30,
30/30 confirmed clicks; Linux/module gate PASS and real EXE artifact uploaded.
Complete structural source `762c3a369a199766ab629007b6b2a3c27885d5e1`: 45 scripts PASS;
Windows 38874685744 SUCCESS, Linux 38874685771 SUCCESS, gate 38874685792 SUCCESS,
Windows recovery 38874685760 SUCCESS (8/8). External frozen EXE workflow PASS;
strict startup 0/20, theme 0/30, confirmed clicks 30/30. Accepted EXE artifact
uploaded. See MODULARIZATION_REPORT_EL.md for exact EXE hash and artifact name.
Professional reliability hardening is a subsequent stage, not renewed extraction.

## Field acceptance gaps

All automated datasets are synthetic/temporary. Local contention and fault
injection do not certify real SMB power loss or NTFS/share ACL. Account identity
simulation does not certify actual Windows logoff/reboot/session switching.
Required: real host + 2+ clients, denied/reconnected share, power-off/replay,
10:00 and 12/24h transitions, long-running responsiveness and blocked-I/O shutdown,
cached cold launch, small/high-DPI displays and real printing. Preserve original
START/END IDs, timestamps, history and pending queue throughout those trials.
No operational data or production deployment is authorized by this work.

All 226 owned function/method annotations now resolve; four extraction import
omissions were restored without algorithm changes. The external EXE driver
reader/focus-fixture failures and their corrections are retained in CONTINUATION.md.

# Architecture and verification map

Branch: `feature/v125-modularization-20261013`. Production main and v1.2.5 are protected.

This is a development audit, not a production acceptance certificate.

## Responsibilities and boundaries

| Area | Current owner | Dependencies / checks |
|---|---|---|
| Settings, runtime files, migrations | position_tracking.py: AppConfig and path helpers | machine_queue; settings integration coverage needed |
| Personnel and roster Excel import | position_tracking_personnel.py | stdlib OOXML; six compatibility/standalone import contracts; legacy facade exports |
| Shared storage and concurrency | SharedEventStore | JSON receipts, SQLite, OS file locks; shared lock and network stress |
| Active positions, START/END | SharedEventStore | booth + officer locks, receipt replay; lifecycle and correction tests |
| Shifts and history | SharedEventStore | SQLite snapshots/session index; shift/archive/history regressions |
| Reports and printing | top-level report functions | docx, openpyxl, Qt PDF; PDF/archive regressions |
| Qt controllers and views | run(): nested MainWindow and widgets | async state/position/network executors; GUI behavior coverage incomplete |
| Durable offline journal | position_tracking_offline | SQLite operations; 15-client restart, contention, durability and replay tests |
| Windows account handoff | position_tracking_handoff | store/journal interfaces; protected original event IDs and replay-order tests |
| Machine queue policy | position_tracking_machine_queue | shared PUBLIC path, legacy queue guard; ACL/two-account simulations |
| Windows sessions | position_tracking_windows_session | WTS; mocked API states, actual session tests still required |
| Local EXE bootstrap | position_tracking_bootstrap | frozen Windows, checksum, PowerShell shortcut; actual offline launch still required |
| Shared normalization | position_tracking_common | stdlib; compatibility contract |

## Dependency direction

UI/controllers → reporting and storage services → personnel/value models and common helpers. Offline/handoff use narrow store interfaces. Entry point reexports legacy names for existing callers/tests. No extracted service should import the entry point. Settings/path providers must preserve application location and runtime override compatibility.

## Known defects / investigation

- Reported mixed light/dark widgets in theme toggle 24 of run 38794439758. Existing code reenables root and window separately and schedules only update(); repaint is deferred. Candidate correction: one top-level update transaction, polish/layout complete while disabled, synchronous whole-tree repaint without processEvents or masking. Windows visual evidence remains mandatory.

- Startup endpoint checks have previously failed (6/20 in run 38788459409). Do not excuse early frames or change limits; new full suspect sequences are retained.

- Artifact download here is blocked by GitHub API access. Public run status is available, CI captures retained evidence; continue diagnosis using reported observations and repeatable tests.

- Previous acceptance matrix contains historical NOT IMPLEMENTED statuses; do not treat those as current facts or silently overwrite historical evidence.


## Validation gaps and field acceptance

All tests use synthetic data and temporary directories. Local contention is not an SMB power-loss/ACL proof. Windows WTS mocks do not prove lock/disconnect/logoff handling on real sessions. Need real Windows SMB host and 2+ clients, ACL-denied/reconnect, host power off, 10:00 shift boundary, logout/reboot, interrupted replay, preserved START/END IDs/timestamps and archive reconciliation. Long-running GUI responsiveness and interactive EXE workflows remain separate acceptance requirements. No access to operational data is needed or authorized.


## Source symbol inventory (audit baseline)

### position_tracking.py

- `_app_dir` (7 lines)
- `_exe_dir` (2 lines)
- `_runtime_root` (16 lines)
- `_open_path` (7 lines)
- `_fallback_settings_path` (6 lines)
- `_settings_path` (2 lines)
- `AppConfig` (53 lines)
- `PersonnelRecord` (13 lines)
- `PersonnelRepository` (206 lines)
- `ShiftRosterRepository` (55 lines)
- `BusyError` (2 lines)
- `SharedEventStore` (1544 lines)
  Methods: `__init__`, `_active_path`, `_lock_path`, `_file_lock`, `officer_lock`, `_atomic_json`, `local_client_id`, `write_client_heartbeat`, `remove_client_heartbeat`, `online_clients`, `send_message`, `acknowledge_message`, `pending_messages`, `message_acknowledgements`, `recent_sent_messages`, `send_close_command`, `pending_commands`, `acknowledge_command`, `_shift_db_write_lock`, `_shift_db_connect`, `_upsert_shift_con`, `_upsert_personnel_session_con`, `_store_personnel_session`, `_has_end_receipt`, `reconcile_pending_sessions`, `_session_row_dict`, `_session_overlaps_clock_window`, `search_personnel_sessions`, `list_personnel_workers`, `list_session_positions`, `_init_shift_db`, `_store_shift_snapshot`, `get_shift`, `_current_report_shift_id`, `_effective_start_timestamp`, `_apply_start_correction`, `correct_active_start`, `get_active`, `_existing_operation_event`, `_write_event`, `start`, `end`, `active_all`, `close_previous_windows_user_positions`, `iter_events`, `iter_all_events`, `completed_sessions_all`, `save_shift`, `_current_shift_path`, `current_shift`, `current_report_shift`, `_person_payload`, `start_officer_shift`, `_sync_active_shift_locked`, `sync_active_shift`, `set_shift_member_state`, `end_officer_shift_member`, `end_officer_shift`, `shift_sessions_v2`, `list_shifts`, `search_finalized_shifts`, `roster_sessions`, `log_admin_action`, `backup_data`, `finalize_shift`, `shift_sessions`
- `_duration_text` (6 lines)
- `build_shift_text` (37 lines)
- `build_roster_shift_text` (39 lines)
- `create_personnel_statistics_xlsx` (118 lines)
- `create_shift_docx` (58 lines)
- `create_shift_pdf` (104 lines)
- `_format_seconds` (4 lines)
- `summarize_personnel_history` (25 lines)
- `create_personnel_history_pdf` (105 lines)
- `archive_shift_pdf` (3 lines)
- `shift_report_title` (18 lines)
- `archive_shift_docx` (7 lines)
- `build_roster_shift_html` (5 lines)
- `_escape_html` (2 lines)
- `build_shift_html` (5 lines)
- `run` (2689 lines)

### position_tracking_bootstrap.py

- `cache_windows_client` (51 lines)

### position_tracking_common.py

- `_clean` (2 lines)
- `_norm_search` (4 lines)
- `_safe_name` (3 lines)

### position_tracking_handoff.py

- `close_previous_windows_user_positions` (70 lines)
- `HandoffBlocked` (2 lines)
- `reconcile_handoff_before_replay` (45 lines)

### position_tracking_machine_queue.py

- `_local_root` (8 lines)
- `_machine_queue_root` (60 lines)

### position_tracking_offline.py

- `OfflineConflict` (2 lines)
- `OfflineJournal` (219 lines)

### position_tracking_rendering.py

- `coherent_widget_update` (22 lines)

### position_tracking_windows_session.py

- `_windows_session_is_active` (37 lines)


## Personnel boundary extracted

`position_tracking_personnel.py` owns immutable personnel value records and read-only
OOXML personnel/roster import. Its only project dependency is the common text helpers;
it imports neither Qt, the central store nor the application entry point. Existing
entry-point class names reexport the same objects. Six contracts cover those identities,
standalone loading, Greek headers, leading-zero IDs, duplicate merging, headerless
known-ID roster, immutable records, invalid input and input-file preservation. The
three class bodies were compared by AST with the pre-extraction source and are unchanged.
The symbol inventory above is the original audit baseline, not a current line count.

## Theme boundary extracted

`position_tracking_theme.py` owns palette dictionaries and pure stylesheet generation.
It imports only common normalization, with no Qt or entry-point import. Palette and
stylesheet ASTs (including CSS string values) match the previous definitions exactly.
Three contracts test independent import, normalization/fallback and actual Qt root
background pixels through light/dark/light; existing application tests exercise 60
whole-window changes. `position_tracking_rendering.py` separately owns coherent paint
transactions, so style data does not depend on presentation or application services.

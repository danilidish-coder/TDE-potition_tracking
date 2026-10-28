# Phase D2 — declared officer, central panel and durable change history

## Approved requirement change

The user's explicit 28 October 2026 instruction supersedes the earlier strong
officer authentication requirement in Issue #10. No new PIN/password, domain,
SSPI/Kerberos or authorization service is required. An existing central AGMS is
declared by the operator and resolved to a name from the central personnel list.
This is attribution, not proof of the person's identity or a certified role.
Anyone with application/share access can declare another listed AGMS. SQL
append-only triggers are integrity controls within this application, not a
security boundary against direct administrative/file/database tampering.
The existing individual-statistics PIN constant and old PIN guard are unchanged.

The exact five previous denial checks remain unchanged at
`tests/central_officer_authorization_regression.py` (SHA256
`7d5c4dd410014a5b33d38cf0b97c444fb3584b0b3a159d4b294181dc347204c6`). Their
actual five FAIL results remain recorded, including run 40723755684. The full
runner still executes them and prints/stores the actual result. Only this exact
retired property is non-mandatory, explicitly under the new user decision. Its
source hash is checked; unexpected errors/timeouts remain mandatory failures.
No START/END/handover, concurrency, recovery, timestamp or GUI gate is exempted.

## Source-only entry points

`python src/position_tracking.py --central-only` opens the lean operator window.
`python src/position_tracking.py --central-officer` opens the separate officer
panel. These commands apply to this source candidate; the approved EXE was not
rebuilt, replaced or configured. The legacy default entry remains unchanged and
must not be run concurrently against this isolated candidate store. There is no
new local roster/profile/business database, bootstrap copy or offline queue in
either central entry. The central share must be available; no fallback exists.

The officer supplies AGMS once. Every command revalidates it against the central
list; no second officer prompt is used. Each substantive command has a default-NO
confirmation. The panel includes:

- shift start/finish, membership approval/exclusion/undo, independent of work;
- central Excel personnel publication with a checked previous revision;
- live table and the existing BoothMapWidget layout;
- explicit remote START/END and active-start time correction with reason;
- existing shift PDF generation and PIN-guarded individual history PDF engine;
- official messages to selected/all online stations and operator acknowledgement;
- a readable on-demand central action history, including old/new values.

Network reads/writes/PDF generation use one owned officer worker with no waiting
queue. UNKNOWN retains the immutable request/action ID and disables new actions
until explicit recheck. A GUI waiting timeout never cancels or disowns its worker.
Operator announcements have one separate bounded worker/10-second heartbeat;
they do not block START/END or add officer controls to that screen.

## Transaction and history boundaries

`position_tracking_officer.py` validates declared participants, confirmation,
intent, reasons and stable command IDs. Existing position START/END code remains
the only position engine. The optional declared-action metadata is prepared with
the existing immutable event. Its append-only officer receipt is inserted in the
same SQLite transaction that accepts the position claim/END. Failure of either
rolls back acceptance; existing bounded recovery reads the original event/ID and
can reconstruct acceptance and its receipt together after a lost ACK.

Each receipt stores action ID/type, declared AGMS/name and list revision,
declared identity status, request and accepted times, target record ID, previous
and new value, reason and result. UPDATE/DELETE of accepted receipt rows is
rejected. Retries return that original receipt; intent/actor collisions do not
rewrite it. They do not re-apply an old live claim.

Active-start corrections use the same central database: exact live START and
previous timestamp are compared inside BEGIN IMMEDIATE. The immutable receipt
and corrected-time head commit together. Every correction retains its own ID and
old/new values; raw START event bytes remain untouched. A delayed correction
cannot change a newer START or overwrite another correction's accepted value.
Existing date/future/reason constraints remain enforced.

`position_tracking_officer_store.py` stages calls to the existing shift/message
methods, then atomically commits their canonical document, immutable action
receipt and shift/report index. Mutable JSONs are central compatibility mirrors;
new officer clients read the canonical SQL document. Missing mirror writes do
not undo accepted data. Repair is bounded. Shift finish never creates physical
END; old D1 pending-member and expected-shift checks remain enforced.

Personnel workbooks are published as complete content-addressed central files.
The SQL current-revision pointer and receipt change together with compare-and-
swap against the confirmed revision. Concurrent or late importers cannot
silently overwrite a newer accepted list. Operator and officer reads resolve
the same pointer and validate its digest; old workbooks/accepted history remain
available. No workstation or Windows-profile copies are written. Invalid input
never replaces the current list. Unaccepted central staging/version evidence
may remain after an interrupted import; it is not a replay/offline queue.

## Validation and limits

Targeted tests cover declared AGMS and confirmation, remote receipt replay,
correction chains and races, audit rollback/recovery, roster publication/CAS,
lost ACK/mirror writes, shift independence, real Qt interactions/worker ownership,
PDF output, official messages/acknowledgements and native source-window exit.
Exact final source SHA, PASS/FAIL/NOT RUN and Actions IDs belong in the existing
`docs/ISSUE_10_STALE_WORKER_STOP_20261027.md` checkpoint, not inferred here.

No new EXE or operational acceptance is claimed. Actual SMB interruption/restart,
ACL behavior and 15 physical Windows stations remain NOT RUN. Production source
4340c418, CURRENT_APPROVED.json, approved EXE, shortcuts and service data are
untouched. D3 historical completed-work admissions are not implemented here.
Stop after D2 source verification; D3 requires a new user instruction and can
reuse this declared-action journal without changing current live positions.

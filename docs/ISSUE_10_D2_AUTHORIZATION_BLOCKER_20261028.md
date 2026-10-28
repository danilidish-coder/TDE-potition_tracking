# Issue #10 D2 — authorization blocker and minimal safe design

**HISTORICAL / SUPERSEDED:** the user's later explicit 28 October decision no
longer requires strong officer authentication. Preserve this diagnosis and its
five FAIL cases as evidence of the accepted security limit. Current requirements
and implementation: `ISSUE_10_D2_DECLARED_OPERATOR_20261028.md` and the latest
section of `ISSUE_10_STALE_WORKER_STOP_20261027.md`. This document is not the
current implementation plan and does not require a new authorization service.

## Decision: BLOCKED; no privileged panel activated

Audit starts at `b5eeb92e5f1394211eb1d50b98c0909f5c0cbb54` on
`feature/central-only-simple-20261027`. Application source is still the D1-tested
`b4cf2020e97d7fdf1ff58671e01a06a264a77ce2`. This checkpoint does not implement D2.
No `src/` change, new officer entry point, credential, policy or service is added.
The central operator preview remains opt-in and has no officer controls.
The legacy default window is NOT an authorized D2 implementation and must not
be presented as secure merely because a name can be selected in it.

## Verified evidence

- `position_tracking_ui_selection.py::_officer_selected` resolves a typed AGMS
  from personnel records; this proves which record was selected, not identity.
- `position_tracking_ui_admin.py::_admin` also selects an officer from AGMS;
  there is no validated authentication session or trusted role check.
- `position_tracking_shifts.py::start_officer_shift`, `set_shift_member_state`,
  `end_officer_shift`, `end_officer_shift_member` accept direct Python calls.
  Shift/START identity checks protect state consistency but do not authenticate
  the caller. A caller-provided PersonnelRecord becomes the audit officer.
- `position_tracking_communication.py::send_message` accepts a sender dictionary.
  An actor label in a JSON audit record is not proof of an authenticated actor.
- `admin_pin_hash` is a settings field, not a verified officer authority.
  The embedded statistics PIN hash is unrelated to secure officer identity.
  Neither is an acceptable substitute and neither is used for D2 authorization.
- `position_tracking_central.py::_store` opens SharedEventStore directly on the
  shared filesystem; StoreIOMixin opens the shared SQLite database for writing.
  No trusted broker/API, SSPI/Kerberos role validation or protected role store
  was found in the application. There is no configured identity binding in this
  execution environment. Organization domain/group/ACL configuration is UNKNOWN,
  not inferred from an environment username or from successful SMB access.

Five strict synthetic regression cases demonstrate missing authorization:
forged Windows label + typed officer starts a shift; a direct business call
excludes a member; another typed officer finalizes the shift; valid shift/START
IDs permit an unauthenticated remote END; a supplied sender sends an official
message. Each MUST raise PermissionError before any write. All five currently
FAIL. The remote-END case changes the live claim and records one committed END
without authenticating its claimed officer. This is a pre-existing authorization
defect in disposable test data, not a newly introduced mutation or production
incident. STOP: do not expose these functions as a secure officer panel.

## Why a client-only role check is insufficient

Hiding buttons, accepting `authorized=True`, trusting USERNAME, selecting an AGMS,
checking a caller-supplied SID, embedding a password/PIN, or loading an editable
role JSON beside client-writable data cannot establish a trust boundary.
Even a real Windows token check only inside the client is bypassable if the same
unprivileged client can write the shared database, personnel and audit files.
Actual SMB/NTFS rights have not been inspected; they are NOT assumed safe.

## Minimal secure target, pending verified infrastructure

Use one trusted process on the existing central Windows host, under a dedicated
service account. Reuse SharedEventStore and its proven START/END/handover logic;
do not build a second position engine. An authenticated request adapter and
server-side officer authorization are the necessary added boundary. This is a
design, not permission to deploy or to reconfigure the service network.

1. A system administrator identifies the isolated test host, actual identity
   authority and individual officer accounts/group. Prefer Windows integrated
   authentication to the central host (verified SSPI/Negotiate configuration,
   Kerberos when available), over validated TLS. Do not assume a domain exists.
   If only host-local accounts exist, verify the supported Windows authentication
   setup and individual accounts before selecting that mode. No shared secret
   embedded in the EXE, environment-variable identity or local allow-all fallback.
2. The central process obtains the authenticated principal/SID from the trusted
   server authentication context and resolves membership against an admin-owned
   officer group/policy. AGMS is a business identifier, mapped centrally to the
   verified officer when needed; it never grants a role. Enforce every privileged
   permission in the business-command dispatcher before any read/write and
   recheck on execution after a queued/delayed job. Unknown/revoked/unavailable
   identity denies access. A test-injected principal is not field authentication.
3. SMB/NTFS deployment must make EXE/config read-only to ordinary clients and
   canonical business data, roster, policy and audit writable only by the trusted
   service/admin identities. Operator mutations must use the same trusted
   boundary too; leaving a direct writable-file path would bypass officer checks.
   This requires verified ACLs and an adapter to existing calls, not a rewrite of
   their transactional rules. No production ACL or shortcut is changed now.
4. Commands reuse immutable operation IDs and expected shift/START/roster
   revisions. Officer START/END require an explicit GUI confirmation and validated
   intent, actual full time and reason where required. Reuse the normal START,
   END and confirmed handover methods. Embed trusted actor/action/reason/time in
   their immutable evidence before commit; never retrofit event bytes afterward.
   Preserve UNKNOWN/read-back semantics, late-worker fencing and idempotency.
5. Shift commands remain independent of physical work. Every privileged change
   records authenticated subject, officer mapping, server timestamp, action,
   immutable command ID, target and reason in protected durable audit evidence.
   Accepted mutation and authoritative audit must commit together; the current
   best-effort supplemental JSON log alone is insufficient for this guarantee.
6. Personnel import is a single central, authorized command using the existing
   OOXML parser. Validate/deduplicate before commit, use an expected roster
   revision to reject lost concurrent updates, retain prior immutable revision
   and trusted audit, publish centrally once. All stations read the accepted
   revision. Never copy rosters to Windows profiles or silently overwrite work.
7. The minimal officer window is separate from the operator screen: shift and
   membership controls, central personnel import, existing live view and explicit
   remote START/END, plus links to existing reports/messages. Access and commands
   require the server authority. All network I/O stays in bounded workers;
   unavailable authorization leaves controls disabled and explains the cause.
   No D3 historical admission/report redesign is part of this step.

## Gate to resume implementation

Obtain a verifiable isolated Windows identity/role and server data-ownership
boundary first. Then implement the smallest adapter and make the five strict
denial cases pass without bypassing the check in test setup. Add real authorized
and revoked-identity tests, GUI bypass, simultaneous stations, actor spoofing,
confirmation, central roster revisions, lost ACK, late workers and preserved
open positions across shift changes. Run all prior gates unchanged, then full
Windows/Linux source CI. Authorized execution, roster publication, D2 remote
START/END, authenticated concurrency and real SMB are NOT RUN now because their
security prerequisite is not available. A green older D1 gate is not D2 approval.

Next input needed is the actual test-host authentication and ACL setup, not an
officer AGMS or a shared password. Do not deploy, build an EXE or start D3.

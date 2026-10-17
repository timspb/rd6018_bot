# D104 — controlled bench-trial readiness

Date: 2026-10-18. Result: `BLOCKED_TOOL_SAFETY`; no trial activation or D097
Enter/Exit was attempted.

## Verified local baseline

- Canonical WSL checkout is clean at `ca77b2f48e5517a18a4a798110672cbdce09dd5f`.
- Its tree is `36a54a52624d0d06ad0f4a2db4ff9bcf739183dd`, equal to the
  accepted D103 candidate tree. The D103 source identity
  `b3cd0174a2918dbbc2ee3f9c908fa14d15089a29` exists in this checkout.
- D090 transaction/release and D102 admission focused tests: **23/23 PASS**;
  `compileall -q .` passed. The D090 transaction test now injects failures at
  every journal phase and immediately before/after each app/venv rename.
- That expanded matrix exposed and fixed a D090 recovery defect at the
  `STOPPED`-journal / pre-backup boundary. `recover()` now resumes the old
  service only after exact baseline equality and fresh independent OFF proof;
  repeated recovery is idempotent through an explicit
  `rollback_without_backup` journal fact. Added no new service, installer,
  endpoint, lease pathway, or production pin.
- Initial full suite on bare system Python 3.12.3 was invalid as a release
  regression: packages including aiohttp and aiogram were missing
  (1153 discovered, 175 errors, 2 failures). No dependencies were installed there.
- Re-ran complete suite from the already installed project Python 3.12 venv:
  **2138 tests OK, 2 skipped**. Local offline test only, not physical evidence.
  Log: E:\CODEX\RD6018_D104_FULL_SUITE_20261018.log.
- Two additional fail-closed tests: tampered preimage and stale OFF proof
  after STOPPED must NOT restart the service. Focused matrix: **25/25 PASS**.
- D103's separately recorded isolated Python 3.11 archive run remains historical
  evidence (2136 OK, 9 skipped), not a D104 execution. It is not refreshed here.

## D090 lifecycle audit

`tools/node104_d090_transaction.py` is the only production transaction owner.
It holds a nonblocking `flock`, validates the pinned host/layout, captures a
fresh two-source OFF proof, durably journals rename phases, preserves app/state/
venv/env/unit preimage, and has a single `recover()` rollback path. Existing
offline tests inject faults around journal, app rename, venv swap, and startup.
`SystemdService.stable()` checks one bot process, restart count, recent logs,
service identity, and expected deployment SHA.

The current owner is intentionally a **production commit** transaction, not a
trial lifecycle: CLI phases are only `prepare|activate|recover`; journal schema
1 admits only D090's pinned `SOURCE_SHA` and `OLD_SHA`; `activate()` requires
the pinned release archive and signed physical acceptance; `recover()` treats
`COMMITTED`/`ROLLED_BACK` as terminal. D090's firmware digest and physical
signer trust pin remain unset. D102 is source-only admission and explicitly
cannot authorize production activation or a physical trial. D095/D096 are
prior edge evidence; D097 through the new Python composition is not physically
accepted. D065 outage/reboot/fault injection is expressly out of scope here.

Consequently, no trial-mode implementation is represented as complete. A
trial requires a schema-versioned journal state distinguishable from
`COMMITTED`, a trial-specific exact source/venv pin, durable preimage identity,
crash recovery at every rename boundary, and an unconditional return to the
verified preimage before any D090 production acceptance. Adding a permissive
`activate_trial` branch to the current class without those paired recovery and
evidence semantics would create precisely the second/ambiguous release owner
prohibited by D104. The local executor also cannot authorize bypass of the
stated system safety denial for real node mutation; no alternate shell or tool
was used for a switch or Enter/Exit.

## D097 physical protocol — prepared, not executed

When the canonical executor and reviewed D104 trial lifecycle are available,
the operator sequence is constrained as follows. This is not an authorization
to execute now.

1. Capture independent fresh HA102 and Native ESP128 readings immediately
   before each transition: HA Output and ESP R18 OFF; R16 Protection `0`; both
   measured V/I `0`; Vset/Iset/OVP/OCP unchanged from the accepted baseline;
   no session, no armed lease, remaining lease `0`; one bot process and exact
   candidate/source/venv inventory. Any stale/missing source, mismatch, or
   unexpected ON means stop and contain using the reviewed owner.
2. Use only the production `PhysicalTestControlPbMode` coordinator via its
   existing root-only AF_UNIX endpoint and `tools/physical_test_autonomous_client.py`.
   First request `status`; do not call raw ESPHome buttons or direct edge APIs.
3. Request `enter` only after all gates pass. Independently record both-source
   readbacks and verify software `HANDS_OFF`, edge autonomous true, lease
   **disarmed** with remaining **0 seconds** (the configured managed-mode
   deadman TTL remains exactly 900 seconds, but is not armed in AUTONOMOUS).
   Confirm generation increased. Do not write
   Output/V/I/OVP/OCP; do not energize or charge.
4. Wait at least 10 seconds between physical actions. Request `exit` through
   the same coordinator. Independently verify `PB_MANAGED` idle, edge
   autonomous false, generation increased again, lease unarmed/remaining 0,
   unchanged setpoints/protection, Output OFF and measured V/I zero.
5. Roll the trial back using the same D090 owner; capture fresh HA/native
   evidence after service stop and after restore, including complete old-app
   inventory identity. Mark only trial evidence as trial; never promote it to
   signed D090 acceptance. No test beyond D097 Enter/Exit is permitted here.

## Fresh read-only node104 observation

At 2026-10-17 14:31:26 UTC, the pinned D091 collector (SHA-256
`c6bf8f456c06da75816976946a9129ccd7619237b6e482874c25a4aa9951ace8`) ran from
stdin under the node's existing Python 3.11 venv. It returned a fresh,
two-source HA102 + Native ESP128 proof: HA and ESP Output OFF, both measured
V/I `0.00/0.00`, active session false, lease unarmed, boot quarantine clear,
native reports fresh, exactly one bot owner and the expected ESPHome identity.
The D091 proof enforces the configured 900-second lease TTL. No actuator or
service call is present in that collector.

A second read-only observation at 2026-10-17 14:28:38 UTC read raw HA and
Native ESP state. Both sources agreed: R18/output state `0`, measured voltage
`0.0 V`, current `0.0 A`, R16 Protection `0`, Vset `13.57 V`, Iset `0.10 A`,
OVP `14.07 V`, OCP `0.20 A`. Native lease state: unarmed, remaining `0.0 s`,
generation `61`, autonomous mode false; all queried Native callbacks were under
1.5 seconds old. HA's separate `autonomous_mode` entity had a stale
`last_reported` timestamp and was not used as current proof. It must be refreshed
before any trial transition.

The node was `rd6018-bot`, machine-id matched D090, service active, MainPID
`69648`, `NRestarts=0`, `DropInPaths=` empty, exactly one bot process. The
service unit and `.env` matched their immutable D090 hashes; marker content
remained old SHA `8b75cca153f00847d84396aba392472bb7552ad4`. The standard
physical-test AF_UNIX socket was absent. The standard client `status` request
returned `FileNotFoundError` for that socket; no Enter/Exit was sent. No
service, unit, environment, app, firmware,
or RD6018 actuator was changed. These observations establish the safe idle
preflight only; they do not establish trial activation or physical acceptance.

Machine-readable status: `D104_BENCH_TRIAL_READINESS_2026-10-18.json`.

## D104 verified follow-up

Both negative pre-backup recovery tests PASS. D090 release trust pins,
hardware guards, and the single deployment owner are unchanged. The physical
trial lifecycle has not been implemented, no Enter/Exit was executed,
and no production/ESPHome state was changed.

Contract correction: During AUTONOMOUS the managed dead-man remains
**disarmed**, remaining **zero**; 900 seconds is only the configured
managed-mode TTL. The earlier report wording suggesting an armed lease
on AUTONOMOUS entry has been corrected.

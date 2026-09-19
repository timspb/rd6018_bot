# RD6018 Live V2/V3 Shadow Observation Run

Статус: **LIVE_V2_V3_SHADOW_VALIDATED**

Дата live read-only snapshot: **2026-09-15 11:03:54 UTC**.

## Runtime mode

- V2: production owner;
- V3: observer/parity analyzer only;
- no deployment, V3 activation, ownership transfer, START/STOP, lease
  operation or physical command.

## Read-only sources

1. HA `192.168.1.102` API — authenticated state read only.
2. node 101 stored WinSCP session — read-only retrieval of
   `/root/rd6018_bot/manual_session_v2.json`.

Secret values were not printed or persisted.

## Captured V2 state

| Field | Observation |
|---|---|
| output | ON |
| battery/profile | Baic72 / Manual |
| phase | MIX |
| lifecycle | active |
| target | 17.5 V / 3.5 A |
| measured | 17.10 V / 3.49 A / 59.67 W |
| temperature | 42 °C internal; 37 °C external |
| protection | code 0; OVP/OCP binary indicators OFF |
| regulation | CC ON; CV OFF |
| lease | armed; TTL 900 s; remaining approximately 777 s at source observation |
| Modbus age | approximately 0.983 s |

The persisted V2 session has no `session_id` or `trace_id`. This is reported as
`UNKNOWN_LEGACY_NO_IDENTITY`; no identity was fabricated.

## V3 shadow construction

The live read-only values were normalized to:

```text
ShadowDecisionInput
  battery/profile: Baic72
  phase: MIX
  program: manual:Baic72
  lifecycle: ACTIVE
  telemetry: 17.10 V / 3.49 A / 42 C
```

V3 shadow decision view used the persisted Manual program targets:
`17.5 V / 3.5 A`, safety result `ALLOW`, and a data-only execution intent.
The intent was compared, never submitted to an executor.

## Parity result

| Component | Result | Evidence |
|---|---|---|
| program | MATCH | Manual Baic72 / `manual:Baic72` |
| phase | MATCH | MIX |
| targets | MATCH | 17.5 V / 3.5 A |
| safety | MATCH | protection 0, lease armed, fresh Modbus age |
| intent | MATCH | data-only setpoint tuple |
| session identity | UNKNOWN | legacy V2 persisted state has no identity |

The parity status is `MATCH` for the observed decision fields. Overall
confidence remains `PARTIAL_LEGACY_IDENTITY_UNKNOWN` because the session
identity/trace fields are absent in the V2 source.

## Safety/no-side-effect validation

The live run performed only HA GET/state reads and one remote file retrieval.
No HA service, ESPHome service, lease button, RD command or physical adapter
was called. V3 did not influence V2, and V2 data was not written back into V3.

## Tests

`tests/test_workstream68_live_shadow_run.py` covers:

- captured live input fields;
- V2/V3 match;
- missing telemetry → `UNKNOWN`;
- report-only safety/target divergence;
- absence of write/control surface.

Result: **5 tests passed**. `compileall` and `git diff --check` passed.

This is a read-only parity snapshot, not production readiness and not an
authorization for canary execution or ownership transfer.

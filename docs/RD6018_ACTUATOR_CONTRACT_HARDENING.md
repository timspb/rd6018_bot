# RD6018 Actuator Contract Hardening

Status: Phase 4.4 contract-only hardening.

## Added typed contracts

### `ActuatorTrigger`

`START_REQUEST`, `STOP_REQUEST`, `SAFETY_CONTAINMENT`, `MANUAL_ACTION`,
`RECOVERY`, `WATCHDOG`, `LEASE_EXPIRY`.

### `RollbackPolicy`

`NONE`, `SAFE_OFF`, `RESTORE_PREVIOUS`, `CONTAIN_AND_LATCH`.

### `SafetyContext`

- telemetry state;
- lease state;
- containment state;
- verification state;
- limits reference.

### `PhysicalVerificationExpectation`

- expected state;
- whether verification is required;
- timeout reference.

## Hardened intent

`ActuatorIntent` now carries trigger, rollback policy, typed safety context and
typed physical verification expectation. Serialization uses explicit enum
values and nested contract objects.

`V2ActuatorExecutionRequest` preserves the same fields, but remains a data-only
request. No executor or runtime bridge is created.

## Rejection rules

- invalid trigger is rejected;
- invalid rollback policy is rejected;
- missing/untyped safety context is rejected;
- missing/untyped verification expectation is rejected;
- physical imports and calls are absent from the intent/adapter layer.

## Explicit non-changes

- no executor;
- no START/ACTIVE wiring;
- no controller/FSM mutation;
- no SafetySupervisor or SafeOutputCoordinator change;
- no HA/ESPHome/physical execution.


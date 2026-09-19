# RD6018 V3 Canary Readiness & Migration Gate — WORKSTREAM 16

## Status

**CANARY_READINESS_DEFINED; activation is BLOCKED.**

Readiness is an evidence gate, not activation. No canary, decision transfer,
lease takeover or physical execution is performed by this model.

## Readiness matrix

`V3CanaryReadinessMatrix` covers architecture, domain, safety, execution,
external integration and observability. Each item records status, evidence,
blocker and owner. The current matrix is blocked by incomplete HA/ESPHome/RD
parity, real readback/rollback validation, and missing complete V3-correlated
live session evidence.

## Entry criteria

`CanaryEntryCriteria` requires all architecture, safety, execution, operational
and external gates plus their evidence. A matrix status or passing unit tests
does not activate a canary.

## Modes

| Mode | V2 | V3 |
|---|---|---|
| 0 Shadow only | owner | observe |
| 1 Decision shadow | execution owner | calculate only |
| 2 Canary decision | execution owner | limited authority, explicit approval |
| 3 Full ownership | compatibility reference | complete owner, separate migration approval |

Each mode has explicit entry/exit/rollback conditions. There is no implicit
ownership transfer.

## Rollback and approval

Rollback triggers cover safety divergence, execution mismatch, telemetry conflict,
lease failure, unknown state and health degradation. The required actions are
revoke authority, return ownership, preserve evidence and notify the operator.

`CanaryApprovalGate` requires an approval owner, required evidence, timestamp,
expiry and revoke condition. Revoke returns a new immutable gate state.

## Current blockers

- **TYPE_B_SAFETY:** live lease/containment and physical safety transfer not
  bench-validated; keep V2/edge owner.
- **TYPE_C_VALIDATION:** direct ESPHome/RD parity and verified readback incomplete.
- **TYPE_D_OPERATIONAL:** V3 observer trace and complete correlated session
  evidence are incomplete.
- **TYPE_E_KNOWN_LIMITATION:** unresolved V2/V3 domain parity decisions remain.

## Operator view

`OperatorDashboardSnapshot.canary_readiness` is optional and read-only. It may
show current mode, readiness status, blockers and evidence freshness without
creating control authority.

## Guardrails

V2 runtime/execution, START/ACTIVE, HA ownership, ESPHome ownership, lease
ownership and physical output remain unchanged. No production control path is
created.


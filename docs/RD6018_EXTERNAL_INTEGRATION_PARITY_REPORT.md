# RD6018 V3 External Integration Parity Report

## Scope and status

This workstream defines and tests the V3 external-integration contracts without
connecting to HA, ESPHome, the RD6018, or a live lease. No V2 runtime, ownership,
START/ACTIVE flow, or physical output was changed.

**Status: BLOCKED — external parity is not production-validated.**

The V3 models are present for comparison and bench preparation. The status is
deliberately not `PRODUCTION_READY`: target-node entity names, command semantics,
freshness, readback, lease, and rollback behavior still require evidence from the
exact deployed external contour and an approved bench run.

## ESPHome parity

The model records the expected boundary:

| Concern | Current external authority | V3 representation | Status |
|---|---|---|---|
| RD telemetry | ESPHome / direct edge telemetry | read-only adapter mapping | NEEDS_VALIDATION |
| output/readback | ESPHome entities and readback path | explicit observed-state verification | NEEDS_VALIDATION |
| lease/dead-man | ESPHome/edge local authority | lease observation only | NEEDS_VALIDATION |
| physical command execution | existing V2/edge path | no live V3 command | BLOCKED |

The exact target ESPHome entities, command services, acknowledgement semantics,
lease generation, armed/tripped state, and remaining TTL must be verified against
the deployed node. The parity layer does not call a client and cannot renew or
alter a lease.

## HA parity

HA is modeled as an external telemetry/control/notification interface, not as the
V3 safety or physical owner. The current configured HA entity inventory is read
from `config/physical/ha102.yaml` for mapping purposes only. V3 does not write HA,
send commands, or infer physical success from an accepted HA request.

Required external evidence remains:

- stale and unavailable sensor behavior;
- conflicting HA versus direct telemetry;
- command acceptance versus observed output state;
- notification delivery and failure behavior.

## Lease parity

The current model preserves the existing ESPHome/edge dead-man as the physical
lease authority, with a 900-second TTL and existing renewal path. Scenarios are
represented for normal renewal, renewal timeout, duplicate owner, expiry, active
restart, and network loss. No second lease owner is created and no renewal is
performed by V3.

## Telemetry arbitration

The modeled preference is:

`fresh ESP direct -> fresh HA -> last known -> unknown`

Every candidate carries source, timestamp, age/freshness, and confidence. A fresh
value conflict is retained as an explicit diagnostic condition; arbitration does
not make a safety or actuator decision.

## Readback and failure matrix

An accepted command is not treated as physical success. The readback model
distinguishes accepted, changed, verified, timeout, mismatch, stale, and
unavailable outcomes. The failure matrix covers transport, ESPHome, HA, lease,
telemetry, and readback failures with detection, decision owner, containment,
verification, and recovery fields.

## Operator visibility

External events are represented as immutable diagnostic records with trace and
correlation identifiers. They are intended for dashboard/operator presentation
through `DiagnosticsDomain`; diagnostics have no side effects and do not execute
commands.

## Blockers before external parity can be accepted

1. Verify the exact deployed ESPHome entities, commands, readback, and dead-man
   contract on the target node.
2. Capture HA/direct telemetry freshness, conflict, and fallback evidence.
3. Prove lease renewal/expiry/restart semantics with one lease owner.
4. Measure RD readback latency, mismatch, stale, and unavailable behavior.
5. Execute the approved bench matrix with rollback evidence.

Until those are complete, this workstream remains a contract/shadow result only.

## Guardrails

- no V2 runtime changes;
- no START or ACTIVE changes;
- no HA writes;
- no ESPHome writes;
- no lease renewal or lease manipulation;
- no physical commands;
- no ownership transfer.


# RD6018 V3 Real Hardware Validation Report — WORKSTREAM 11

## Status

**BLOCKED** — read-only validation contracts and tests are prepared, but no
real HA, ESPHome, RD transport, lease or hardware observations were collected
in this workstream. The status is intentionally not `PRODUCTION_READY`.

## Operating boundary

V2 remains the production and physical owner. V3 is an observer, validator and
parity analyzer. No commands, writes, lease renewal, ownership transfer, START,
ACTIVE change, or emergency action was performed.

## Prepared validation models

- `RealTelemetryValidationModel`: source, timestamp, age, confidence,
  availability, stale/missing/conflicting values.
- `RealReadbackValidationModel`: command history is evidence only; accepted
  command is never treated as physical verification. It distinguishes verified,
  unavailable, stale and mismatch states.
- `ESPHomeObservationReport`: entities, states, availability and lease-related
  read-only information.
- `HAObservationReport`: entities, sensors and availability without HA writes.
- `RealLeaseObservationReport`: owner, renewal/expiry observations and fail-safe
  result without lease manipulation.
- shadow comparison: V2 observed behavior versus V3 expected model, classified
  as MATCH, EXPECTED_DIFFERENCE, WARNING or BLOCKER.

## Required controlled evidence

The next approved read-only observation must capture ESPHome telemetry/entities,
HA telemetry/entities, RD readback, lease state and timestamps. It must also
record trace/session identifiers and route all findings through DiagnosticsDomain
to OperatorDashboardSnapshot. No automatic commands are permitted.

## Blockers

1. No fresh real-contour telemetry evidence is attached.
2. No real readback/physical-state evidence is attached.
3. ESPHome entity and lease observations are not verified on the target node.
4. HA availability/conflict behavior is not verified.
5. No controlled bench/rollback evidence exists.

## Guardrails

V2 runtime, START, ACTIVE, HA ownership, ESPHome ownership, lease ownership and
physical output remain unchanged. This report does not authorize production
integration or physical execution.

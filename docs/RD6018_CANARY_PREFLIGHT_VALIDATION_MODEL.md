# RD6018 V3 Canary Preflight Validation — WORKSTREAM 17

## Status

**CANARY_PREFLIGHT_READY as a non-activating evaluator; current real readiness
remains BLOCKED.**

`CanaryPreflightValidator` evaluates supplied readiness, health, shadow evidence,
diagnostics, approval and blocker snapshots. It returns `ALLOWED`, `WARNING` or
`BLOCKED` with named checks, evidence and blockers.

## Checks

The evaluator covers architecture, domain, safety, execution, observability and
external readiness through the supplied matrix, then independently checks:

- evidence identity, timestamp and freshness;
- current health;
- approval owner, expiry and revoke state;
- rollback procedure and owner;
- active blocker registry;
- diagnostic references.

Critical missing evidence, safety/ownership/execution blockers, invalid approval
or missing rollback readiness produce `BLOCKED`. Stale but non-critical evidence
produces `WARNING`; critically stale evidence produces `BLOCKED`.

## Operator view

`CanaryPreflightSnapshot` is read-only and contains status, failed checks,
blockers, evaluation time and evidence freshness. It is exposed through the
optional `OperatorDashboardSnapshot.canary_preflight` field.

## Guardrails

The evaluator has no activation method, authority transfer, transport adapter,
lease operation or physical call. V2 remains production owner. No START/ACTIVE,
HA, ESPHome, lease or physical behavior changed.


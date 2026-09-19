# RD6018 V3 Shadow Runtime Evidence Aggregation — WORKSTREAM 15

## Status

**SHADOW_EVIDENCE_AGGREGATION_READY.**

This layer aggregates evidence only. It does not execute decisions, restore
runtime state, call transport, renew leases or change ownership.

## Bundle and correlation

`ShadowEvidenceBundle` correlates metadata, canonical events, current phase and
session state, telemetry, execution observations, safety/containment evidence,
diagnostic references, health and V2/V3 divergences. Every event and observation
is associated with session/trace identity and a timestamp.

`EvidenceCorrelationEngine` detects missing correlation, missing timestamps,
conflicting sessions and out-of-order events.

## Replay

`ShadowReplayEngine` reconstructs a `CanonicalTimelineSnapshot` and produces
analysis decisions from the event stream. It returns
`execution_performed=False` and has no adapter, transport or actuator
dependency.

## Persistence boundary

`ShadowRuntimeEvidenceNamespace` is the analytical namespace
`shadow_runtime_evidence`. It stores bundles and replay results for the contract
and explicitly rejects runtime restore. Evidence cannot become FSM, lease,
safety or actuator state.

## Operator visibility

`OperatorDashboardSnapshot.shadow_status` is optional and backward-compatible.
`ShadowHealthSnapshot` and `ShadowDashboardStatus` expose collector health,
freshness, evidence count, last divergence and parity state without side effects.

## Guardrails

V2 runtime/execution, START/ACTIVE, HA, ESPHome, lease and physical output are
unchanged. No production execution path is created.


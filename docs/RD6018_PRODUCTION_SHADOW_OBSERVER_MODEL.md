# RD6018 production shadow observer — Phase 10.0

## Purpose

`ShadowObservationSession` models the V3 observer beside the existing V2
runtime. It receives a copy of the input context and an already-produced V2
decision, computes a V3 decision through an injected provider, compares both,
explains divergences and records the result in memory.

```text
V2 input copy
     |
     v
ShadowObservationSession
     +-- V3 decision provider
     +-- V2/V3 comparison
     +-- divergence explanation
     +-- DiagnosticsDomain
     +-- in-memory observation records
```

## Observation record

Each `ShadowObservationRecord` contains:

- `trace_id`;
- mirrored input snapshot;
- V2 decision;
- V3 decision;
- comparison result;
- divergence explanation;
- diagnostic event.

Records are held only in the session object. No file, database or production
state is written.

## Safety boundary

The observer does not execute `ActuatorIntent`, call `ExecutionDispatcher`,
send HA/ESP commands, mutate V2 session/FSM, or change START/ACTIVE. The V3
provider is injected as a pure decision function and must return a
`DecisionSnapshot` or `None`.

Production V2 runtime remains the only active runtime owner. This phase adds no
production startup hook.

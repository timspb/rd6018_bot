# RD6018 V3 Operator Observability & Diagnostics

## Boundary

```text
V3 modules -> DiagnosticsDomain -> DiagnosticSnapshot/Health -> UI adapter
```

The UI is read-only presentation. It does not own diagnostics, runtime health,
safety decisions, execution state or transport state.

## DiagnosticsDomain

`v3_core.observability.DiagnosticsDomain` is the single live in-memory source
for immutable `DiagnosticEvent` records. Each event contains event id,
timestamp, severity, category, source, component, message, trace id, session
id, correlation id and state context.

Categories: `DOMAIN`, `SAFETY`, `EXECUTION`, `TRANSPORT`, `CONFIGURATION`,
`PERSISTENCE`, `UI`, `OPERATOR`.

Severities: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.

The domain does not call Python logging, Telegram, runtime, hardware, HA,
ESPHome or persistence. Historical storage is an outer persistence concern.

## TraceContext

Every event requires `session_id`, `trace_id` and `correlation_id`.
`TraceContext.create()` starts a trace; `child()` preserves session/trace and
creates a new correlation id. Missing identity is rejected.

Expected continuity:

```text
START -> phase -> actuator intent -> safety/execution -> STOP
  \________________ same session/trace __________________/
```

## SystemHealthSnapshot

The snapshot aggregates runtime, domain, safety, execution, transport,
configuration, persistence and UI statuses. Overall status is conservative:
`FAILED` dominates `DEGRADED`, which dominates `WARNING`, which dominates
`HEALTHY`.

## OperatorDashboardSnapshot

The UI receives one read model containing current charge, meaningful timeline
events, health, safety state, last execution result, configuration warnings,
diagnostics and alerts. It does not receive raw runtime state or call back into
domain/execution.

## OperatorAlert

`OperatorAlert` normalizes fault presentation with severity, source, timestamp,
description, affected component, recommended action and resolved state.
Resolution returns a new immutable value.

## History

`DiagnosticHistory` is a read-only query contract over supplied events. Live
diagnostics remain memory-owned; historical persistence is external and no
restore authority is implied.

## Validation

`tests/test_workstream9_observability.py` covers event creation, trace
continuity, missing trace rejection, health aggregation, dashboard generation,
alert lifecycle, session filtering, safety/execution visibility and no physical
side effects.

Status: `OPERATOR_OBSERVABILITY_READY` for the pure V3 observability contract.

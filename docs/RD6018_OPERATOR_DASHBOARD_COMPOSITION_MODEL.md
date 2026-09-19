# RD6018 V3 Operator Dashboard Composition — WORKSTREAM 33

## Status

`OPERATOR_DASHBOARD_READY`.

`OperatorDashboardComposer` builds one immutable `OperatorDashboardState` from
one `OperatorRuntimeView`. Panels do not independently read telemetry,
diagnostics, parity or canary sources.

## Panels

The snapshot contains current session, current-session timeline, telemetry,
decision explanation, safety, diagnostics, V2/V3 parity and Canary readiness.
The timeline is attached only when its session identity matches the current
observation. Otherwise it is shown as `UNKNOWN` rather than guessed.

Missing telemetry, stale sources, unknown phase and legacy missing identity are
visible as degraded/unknown data. Historical events are never promoted to a
current lifecycle event.

The dashboard is explicitly `observe_only=true`; it contains no command,
START/STOP, lease or physical execution path.

# RD6018 interface boundary model (Phase 5.3)

Статус: contracts + architecture only. Runtime composition, HA, ESPHome и
physical execution не подключены.

## UI Module

UI owns Telegram commands/callback presentation, dashboard rendering, operator
notifications and formatting of domain/application results.

UI consumes immutable snapshots, allowed operator actions and feedback results.
UI exports operator intents and presentation events.

UI must not own or import:

- charge FSM or domain transition logic;
- safety decisions or containment owners;
- HA clients or ESPHome clients;
- RD transport/control providers;
- physical/output implementations.

The UI may request an application action, but it cannot decide whether a charge
is safe or execute a command.

## Telemetry Boundary

`TelemetryProvider` is read-only and returns transport-neutral snapshots:

- voltage;
- current;
- temperature;
- output state;
- capture timestamp and freshness metadata at the consuming boundary.

Telemetry is consumed by diagnostics, dashboard, preflight and domain
evaluation. It does not expose setpoint or output command methods.

## Control Boundary

`ControlProvider` contains only command-shaped operations:

- set voltage;
- set current;
- output on;
- output off.

It is an execution boundary, not a domain or UI dependency. Safety/output
ownership remains outside this Phase 5.3 contract and is not replaced.

## RD Transport Boundary

`RDTransport` is the common interface for reading telemetry/readback and issuing
setpoint/output operations. `HARDAdapter` and `ESPDirectRDAdapter` are separate
adapter boundaries implementing the same contract. Their implementations are
not created here.

```text
UI -> application intent/feedback only
domain -> data-only decision
TelemetryProvider -> measurements/readback
ControlProvider/RDTransport -> existing execution owner (future boundary)
```

The domain cannot select HA versus ESP, retry transport, renew a lease, or
decide containment. Adapter selection belongs to composition and is deferred.

## Separation invariants

1. A type implementing `TelemetryProvider` is not required to implement
   `ControlProvider`.
2. Domain modules depend on measurement data, not on either provider.
3. UI has no path to `ControlProvider` or `RDTransport`.
4. Both adapter boundaries have identical operation names and result shapes.
5. No contract in this document performs I/O by itself.

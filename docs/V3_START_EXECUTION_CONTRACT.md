# V3 START execution contract

## Boundary

```text
RuntimeStartService
        |
        v
StartExecutionRequest
        |
        v
StartExecutionPort
        |
        v
DryRunExecutionPort
```

`StartExecutionRequest` is an immutable data-only handoff. It contains the
approved plan, trace identity, ownership/session/safety decisions, telemetry
evidence and execution metadata. It contains no HA client, controller,
connector, physical object or mutable runtime state.

## Current implementation

`DryRunExecutionPort` accepts only a validated request and returns a contract
acknowledgement. It never calls `controller.start()`, mutates FSM/session,
writes HA, changes setpoints, enables Output or accesses a physical connector.

`ACTIVE` is not implemented as an executable path and remains outside
production composition.

## Remaining work before ACTIVE

- select and approve the single execution owner;
- connect only through a separately reviewed production port;
- preserve V2 rollback and verified-OFF behavior;
- complete bench validation of the full START transaction;
- add production import-isolation and feature-gate checks at activation time.


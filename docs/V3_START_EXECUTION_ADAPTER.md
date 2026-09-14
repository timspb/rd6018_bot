# V3 START execution adapter

## Current boundary

```text
ApprovedStartPlan
        |
        v
RuntimeStartService
        |
        v
StartExecutionAdapter
        |
        +-- SHADOW: trace only
        +-- DRY_RUN: handoff plan only
        +-- ACTIVE: feature-gated, disabled
        |
        v
existing V2 START path (not connected)
```

`StartExecutionAdapter` does not import or call the controller, HA, safety
coordinator, output adapter, physical transport, or FSM. It only validates the
approved plan and describes the future handoff.

## Modes

### SHADOW

Builds `StartExecutionTrace`; no mutation is permitted.

### DRY_RUN

Runs the same ownership/session/safety/output-off checks and returns an immutable
`StartHandoffPlan` with `physical_execution=False`.

### ACTIVE

Disabled by default. It is not wired into `bot.py` or the production callback
path. Enabling it requires a separate approval after session ownership, FSM
ownership, rollback and verified-OFF semantics have been bench-validated.

## Remaining blockers

- define the single production owner of controller/session handoff;
- prove rollback and failed-start verified-OFF behavior;
- preserve V2 transactional ordering and readback semantics;
- add a dedicated dry-run integration gate;
- perform physical bench validation before any ACTIVE enablement.


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
        +-- ACTIVE: existing V2 transaction handoff
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

The production route reaches the existing V2 transaction owner only after
`StartPreflightService` passes. The adapter still does not own controller,
session, safety or physical execution.

## Runtime boundary

V2 remains the single controller and physical owner; rollback and verified-OFF
semantics remain in the existing V2 path.

# V3 START DRY_RUN integration gate

## Flow

```text
ApprovedStartPlan
        |
        v
RuntimeStartService / StartExecutionAdapter
        |
        v
StartDryRunIntegrationGate
        |
        +-- read V2 ownership/controller/session
        +-- read fresh HA telemetry
        +-- inspect handoff probe
        +-- produce rollback plan
        |
        v
StartDryRunReport
```

## What is checked

- `HANDS_OFF` ownership;
- active controller session;
- fresh telemetry and Output OFF;
- controller handoff availability through a read-only probe;
- V2 transaction ordering;
- verified-OFF requirement for a future failed execution.

## What is prohibited

The gate never calls `controller.start()`, session/FSM mutators, HA writes,
setpoint methods, Output enable or physical transports. The report always marks
physical execution as `dry_run_physical_execution_disabled`.

## Current status

Successful and denied dry-run paths remain available for preview/tests,
including simulated failed handoff and Output-ON fail-closed behavior. The
production Telegram path uses the same preflight and port with the existing V2
transaction owner.

## Runtime boundary

The dry-run gate remains non-actuating. Physical execution is still limited to
the canonical preflight → ExecutionPort → V2 owner path.

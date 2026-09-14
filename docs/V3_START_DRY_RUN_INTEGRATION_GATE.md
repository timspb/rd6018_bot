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

Successful and denied dry-run paths are tested, including a simulated failed
handoff and Output-ON fail-closed behavior. ACTIVE remains disabled and is not
wired into `bot.py`.

## Blockers before ACTIVE

1. approve the production controller/session handoff owner;
2. prove rollback and verified-OFF on failed physical start;
3. preserve V2 transaction/readback ordering on a bench;
4. complete physical START bench validation;
5. explicitly authorize ACTIVE and wire it only after those gates pass.


# V3 ProductionStartExecutionPort

## Current gated wiring

```text
RuntimeStartService
        ↓
ProductionStartExecutionPort
        ↓
V2StartTransactionAdapter
        ↓
start_profile_transactional()
```

The port currently performs shadow/dry-run routing only. It is not wired into
the Telegram START callback, so the existing V2 callback remains the single
authoritative production START route.

## Modes

- `SHADOW`: creates trace and immutable request;
- `DRY_RUN`: performs full data routing and adapter preparation, without calling
  the V2 transaction owner;
- `ACTIVE`: unconditionally rejected as `active_execution_disabled`.

`trace_id` is carried through `StartExecutionRequest`, V2 transaction input and
normalized `StartExecutionResult`.

## Current safety boundary

No controller, FSM, session, HA, setpoint or physical operation is performed by
the port. Existing V2 remains the execution owner.

## Blockers before bench ACTIVE

1. approve the production callback handoff without creating a second START route;
2. validate real V2 transaction outcome mapping and rollback states;
3. bench-validate verified OFF and containment for failed enable;
4. retain feature-gate and production import isolation;
5. explicitly authorize ACTIVE after all gates pass.


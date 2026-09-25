# V3 ProductionStartExecutionPort

## Current wiring

```text
RuntimeStartService
        ↓
ProductionStartExecutionPort
        ↓
V2StartTransactionAdapter
        ↓
start_profile_transactional()
```

The Telegram START route performs `StartPreflightService` checks and then uses
this port to reach the preserved V2 transaction owner. The port does not own
chemistry, session state, safety policy or hardware.

## Modes

- `SHADOW`: creates trace and immutable request;
- `DRY_RUN`: performs full data routing and adapter preparation, without calling
  the V2 transaction owner;
- `ACTIVE`: executes the existing async V2 transaction after preflight.

`trace_id` is carried through `StartExecutionRequest`, V2 transaction input and
normalized `StartExecutionResult`.

## Current safety boundary

No controller, FSM, session, HA, setpoint or physical operation is performed by
the port. Existing V2 remains the execution owner.

## Runtime requirements

The existing V2 transaction owner remains responsible for verified readback,
rollback, lease and physical safety. DRY_RUN remains available explicitly for
preview and tests; it is not the production Telegram default.

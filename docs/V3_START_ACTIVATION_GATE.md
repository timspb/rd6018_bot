# V3 START activation gate

## Policy

```text
StartActivationPolicy
        |
        +-- SHADOW  -> allowed
        +-- DRY_RUN -> allowed
        +-- ACTIVE  -> all explicit gates required
```

ACTIVE requires all of:

- `explicit_active_enable=True`;
- `bench_validation_passed=True`;
- `rollback_validation_passed=True`;
- `physical_gate_passed=True`;
- policy execution mode set to `ACTIVE`.

The default policy is fail-closed and rejects ACTIVE.

## Integration

The policy is consulted only by `ProductionStartExecutionPort`. It does not
change controller, FSM, SafetySupervisor, SafeOutputCoordinator or physical
transport behavior.

## Current status

SHADOW and DRY_RUN remain available. ACTIVE is not enabled in production and
there is no Telegram wiring to this port.


# RD6018 Actuator Intent Adapter Model

Status: Phase 4.2 dry-run preparation.

## Boundary

```text
ActuatorIntent
      |
      v
ActuatorIntentAdapter.adapt()
      |
      v
V2ActuatorExecutionRequest
      |
      v
(future V2 execution owner; not called in Phase 4.2)
```

The adapter validates operation, owner, source and safety context. It produces
a transport-free request only.

## Supported operations

- `OUTPUT_ON`
- `OUTPUT_OFF`
- `SET_VOLTAGE`
- `SET_CURRENT`

An operation is accepted only with an owner already present in the Phase 4.1
ownership inventory. UI/Telegram/direct-physical sources and explicitly blocked
safety contexts are rejected.

## Explicit non-responsibilities

The adapter does not:

- call `ChargeController` or mutate FSM/session state;
- call `SafeOutputCoordinator`;
- call HA or ESPHome;
- enable/disable Output;
- write voltage/current setpoints;
- replace the existing V2 owner or its safety behavior.

## Gate for future wiring

Before this request can be handed to a real owner, a later phase must prove
operation parity, owner parity, rollback mapping, OFF verification and absence
of duplicate production execution paths. Phase 4.2 intentionally stops before
that handoff.


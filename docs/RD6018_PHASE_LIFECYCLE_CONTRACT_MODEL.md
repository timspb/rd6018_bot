# RD6018 V3 Phase Lifecycle Contract Model

Статус: **PHASE_LIFECYCLE_MODEL_READY**

Создан pure data-only слой `application/charge_engine/phases/`.

## Contracts

- `PhaseContract` — entry/exit conditions, confirmations, timeout, interruption и recovery policy;
- `DeltaPolicy` — generic start/completion evidence, timeout, measurements и reason;
- `HoldPolicy` — start, duration, exit и interruption semantics;
- `PhaseLifecycleRegistry` — immutable contract lookup без chemistry/program branching.

Canonical lifecycle phases:

```text
PREP -> MAIN -> DESULFATION -> MIX -> HOLD -> SAFE_WAIT -> DONE
```

Каждая phase имеет отдельный contract. Targets, chemistry, battery identity, transport и safety actions находятся вне этого слоя.

## Safety boundary

Phase contracts только описывают evidence и state transitions:

```text
PhaseContract
    -> SafetyPolicy (external)
    -> Decision
```

Контракты не вызывают output, OFF, HA, ESPHome, Modbus, lease или transport.

## Validation

Добавлены tests `tests/test_workstream51_phase_contracts.py`:

- все семь canonical phases имеют contracts;
- Delta и Hold contracts валидируются;
- timeout/interruption policy проверяются;
- contracts immutable;
- physical/safety side effects отсутствуют.

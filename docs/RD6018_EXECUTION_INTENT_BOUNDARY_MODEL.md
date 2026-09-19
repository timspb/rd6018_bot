# RD6018 V3 Charge Decision → Execution Intent Boundary

Статус: **EXECUTION_INTENT_BOUNDARY_READY**

## 1. Boundary

```text
ChargeEngine
    |
    v
ChargeDecision
    |
    v
DecisionIntentMapper
    |
    v
ExecutionIntent
    |
    v
future execution layer
```

`ExecutionIntent` — immutable data-only contract. Он не вызывает RD, HA, ESPHome, Modbus, controller или физический транспорт.

## 2. Decision contract

`ChargeDecision` теперь содержит:

- `program_id`;
- `current_phase`;
- target voltage/current;
- reason;
- conditions;
- confidence;
- deterministic `decision_id`;
- next transition criteria.

## 3. ExecutionIntent

Поля:

- `requested_voltage_v`;
- `requested_current_a`;
- `requested_mode`;
- `source_decision_id`;
- immutable `SafetyContext`.

Intent описывает request, но не означает, что команда разрешена или исполнена.

## 4. Safety validation

`SafetyPolicy` возвращает `IntentValidationResult`:

- `ALLOWED` — intent принят без изменения;
- `LIMITED` — setpoints ограничены политикой;
- `DENIED` — intent не создаётся для execution handoff.

Safety policy не выполняет shutdown или physical action. Она только валидирует/ограничивает data contract.

## 5. Transport independence

В `application/execution_intent/` отсутствуют:

- HA clients;
- ESPHome clients;
- RD API;
- Modbus;
- V2/controller imports;
- physical calls.

## 6. Tests

Проверены:

- decision → intent;
- safety allow;
- safety limit;
- safety reject;
- deterministic conversion;
- missing setpoints;
- отсутствие physical dependencies.

Production wiring не добавлялся.

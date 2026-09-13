# V3 Phase 7 — Runtime charge shadow

Статус: shadow-only integration

Baseline: `fdeca527b78025c2604a88ba43dbd59de7eb76b8`

## Data flow

```text
RuntimeApp
    ↓
ChargeService
    ├── BatteryProfile
    ├── ProgramRegistry
    └── ChargeEngine
            ↓
       ChargeIntent
            ↓
   DecisionValidationResult
```

`RuntimeApp` создаёт `ChargeService` с registry и injectable clock. Service
выбирает программу, передаёт domain snapshots в `ChargeEngine` и возвращает
`ChargeRuntimeSnapshot` с active program, battery profile, intent и timestamp.

`shadow_tick` сравнивает полученный intent с representative expected intent.
Это отдельный read-only path: текущий production decision не вызывается и не
заменяется, а native intent никуда не отправляется.

## Ownership

- RuntimeApp владеет service reference и его lifecycle.
- ChargeService владеет только program selection/evaluation orchestration.
- Registry владеет lookup/creation.
- Engine/programs владеют только pure domain decisions.
- Safety, ownership, lease, HA, RD/ESP, Output, persistence и Telegram не
  входят в этот путь.

## Shadow mode and migration gate

В Phase 7 shadow может работать рядом с existing production decision только как
наблюдение/comparison. `MATCH` фиксирует совпадение конкретного representative
case; `MISMATCH` блокирует перенос соответствующего режима до forensic анализа.
Ни один результат shadow не является разрешением actuator operation.

## Remaining migration

Остаются legacy controller/FSM, production tick/action executor, restore,
safety/lease integration и Telegram UI. Следующий этап требует explicit wiring
к read-only measurements и полному parity corpus; только после этого можно
обсуждать safety integration. Production runtime, Output и ESPHome не изменялись.

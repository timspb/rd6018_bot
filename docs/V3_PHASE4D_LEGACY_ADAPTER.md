# V3 Phase 4D — Legacy Charge Program Adapter

Статус: comparison adapter only

Baseline: `242aa056929949175b8e3fc30b95cb0ac11f0249`

## Что адаптировано

Добавлен первый adapter:

```text
runtime/charge/adapters/legacy.py
LegacyChargeProgramAdapter
```

Он принимает `BatteryProfile` и pure legacy/V2 decision callable, передаёт ему
`BatteryProfile`, `ChargeState` и `Measurements`, а mapping результата переводит
в `ChargeIntent`:

```text
legacy decision mapping
  → LegacyChargeProgramAdapter
  → ChargeIntent
```

Для первого comparison slice выбран общий Minimum-style decision shape (`set_voltage`,
`set_current`, `next_stage`, `completed`, `log_event`). Реальный Minimum/Delta/Manual
алгоритм не переносился и production controller не подключался.

## Boundary restrictions

Adapter не создаёт и не получает HA, RD, Telegram, output, lease, safety или
persistence dependencies. Если legacy result содержит actuator commands
(`turn_on`, `turn_off`, `emergency_stop`, `full_reset`), adapter отклоняет его
вместо скрытого выполнения или молчаливого пересечения boundary.

Таким образом:

```text
ChargeEngine + Adapter → ChargeIntent
                         ↓
                    future SafetyEngine
```

`ChargeIntent` не применяется к физическому устройству.

## Comparison evidence

`tests/test_v3_legacy_adapter.py` сравнивает representative legacy decision с
результатом `ChargeEngine + LegacyChargeProgramAdapter` по voltage, current,
stage, completion и reason. Отдельно проверяется rejection actuator result и
отсутствие внешних imports.

## Что осталось legacy

- `ChargeController`, V2/legacy FSM и action executor;
- фактические Minimum/Delta/Manual decision algorithms;
- production composition и all HA/RD actuator paths;
- persistence, lease и safety wrappers.

Adapter пока не подключён к production и не заменяет controller. Следующий шаг
допустим только для отдельной program decision с parity tests; любой output,
safety или ownership migration остаётся за отдельным gate.

Production runtime, FSM, UI, ESPHome/YAML и node 101 не изменялись.

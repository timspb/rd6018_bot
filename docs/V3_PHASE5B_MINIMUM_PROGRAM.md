# V3 Phase 5B — Native MinimumProgram

Статус: native pure program, не подключён к production

Baseline: `679a7c78f9c9ea38e72c47f7932c137a6eec07aa`

## Что создано

Добавлены `MinimumConfig` и `MinimumProgram(ChargeProgram)`. Program получает
`ChargeState`, `Measurements` и `BatteryProfile`, вычисляет configured completion
condition и возвращает только `ChargeIntent`.

```text
ChargeState + Measurements + BatteryProfile + MinimumConfig
                         ↓
                   MinimumProgram
                         ↓
                    ChargeIntent
```

В active state intent содержит configured target V/I и `active_stage`. При
достижении configured current (и optional voltage) condition intent помечается
`completed`, получает `completed_stage` и `completion_reason`. Это pure program
logic; safety envelope and physical authorization находятся вне программы.

## Shadow comparison

Representative legacy Minimum mapping сравнивается с native result через
`ChargeDecisionShadow` по voltage, current, stage, completion и reason. В тестах
зафиксированы два результата: ожидаемый `MATCH` и явный field-level `MISMATCH`
(`target_voltage`). Расхождение не исправляется молча.

## Ограничения

Program не импортирует и не вызывает HA, RD/ESP, Telegram, persistence, lease,
safety или actuator methods. Legacy Minimum, V2/legacy controller, FSM и
production runtime не подключались и не изменялись.

При переносе реального Minimum behavior следующим gate должны стать полное
сопоставление chemistry/recipe thresholds, confirmation/hold semantics,
timeout/stop paths и parity tests; representative match не равен production
acceptance.

ESPHome/YAML, node 101 и firmware не изменялись.

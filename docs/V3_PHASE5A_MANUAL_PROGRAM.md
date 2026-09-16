# V3 Phase 5A — Native ManualProgram

Статус: native pure program, не подключён к production

Baseline: `72779eb1da284d02e528f9a886caf5527a63119c`

## Что создано

Добавлены `ManualTargets` и `ManualProgram(ChargeProgram)`:

```text
BatteryProfile
      +
ManualTargets (domain input)
      +
ChargeState + Measurements
      ↓
ManualProgram
      ↓
ChargeIntent
```

Программа отображает объявленные manual voltage/current в intent, выбирает
следующий stage из domain input или state и возвращает reason. Она не изменяет
state, не завершает сессию автоматически и не выполняет physical action.

## Shadow comparison

`ChargeDecisionShadow` сравнивает representative legacy Manual mapping с
native `ManualProgram` intent по voltage, current, stage, completion и reason.
Тест также проверяет обнаружение mismatch по конкретному полю.

## Ограничения и ownership

`ManualProgram` не импортирует и не получает Telegram, HA, RD/ESP, lease,
persistence или safety. Она не вызывает `turn_on`, `turn_off` и setpoint
methods. Любой intent должен в будущем пройти существующую SafetyEngine и
OutputAdapter boundary.

Legacy Manual, `ManualSessionManager`, production controller, FSM и production
runtime остаются без изменений. Native program к production не подключена и не
заменяет legacy Manual.

Следующий шаг — только после comparison evidence: оценить parity полного Manual
contract, включая stop/completion semantics, затем отдельный safety/UI migration
gate.

ESPHome/YAML, node 101 и firmware не изменялись.

# V3 Phase 4B — battery domain model

Статус: pure domain model only

Baseline: `b455f75759018c328d95fe53fb7c3c9224cefd93`

## Что создано

Добавлены data-only модели:

- `ChemistryProfile`: `AGM`, `EFB`, `CALCIUM`;
- `ChargeLimits`: max/absorption/float voltage, max current и optional
  temperature-compensation parameters;
- `BatteryProfile`: chemistry, capacity, optional manufacturer, nominal voltage
  и declared charge limits.

Модели проверяют только целостность входных данных (положительные значения и
порядок voltage limits). Они не являются charge programs и не знают о способе
управления зарядом.

## Разделение battery и program

Правильная композиция:

```text
BatteryProfile(chemistry=AGM)
        +
ChargeProgram(Standard)
        → ChargeIntent
```

Химия описывает battery identity и её envelope. Program описывает алгоритм
оценки state/measurements. Поэтому `AGMProgram`, `EFBProgram` и
`CalciumProgram` намеренно не создавались.

## Ownership и extension path

- `BatteryProfile` принадлежит domain layer и является immutable snapshot.
- `ChargeLimits` принадлежит battery profile, но не выдаёт actuator permission.
- Будущие программы получают профиль как входные данные и возвращают
  `ChargeIntent` через Phase 4A contract.
- SafetyEngine отдельно проверяет intent; domain models не вызывают HA/RD,
  Telegram, controller, lease или output.

Существующие controller/program implementations остаются legacy/current V2 и не
подключены к новым моделям. Расширение новыми chemistry — добавление enum value
и соответствующих данных профиля, без создания chemistry-specific program class.

## Проверки

`tests/test_v3_battery_domain.py` проверяет AGM/EFB/CALCIUM, limits validation,
profile validation и отсутствие внешних интеграций/chemistry-specific program
classes.

Runtime behavior, production controller, FSM, UI, ESPHome/YAML и node 101 не
изменялись.

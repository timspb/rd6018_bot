# V3 Phase 4C — ChargeEngine boundary

Статус: pure orchestration boundary only

Baseline: `3e17fc18dcff594a1cefa52e5eb50db21f82d4a9`

## Что создано

Добавлены:

- `Measurements` — immutable snapshot voltage/current/temperature/time без
  истории;
- `ChargeEngine` — принимает `BatteryProfile` и active `ChargeProgram`;
- `ChargeEngine.evaluate(state, measurements)` — делегирует evaluation программе
  и возвращает `ChargeIntent`.

```text
BatteryProfile + ChargeState + Measurements
                 ↓
             ChargeEngine
                 ↓
            ChargeProgram
                 ↓
            ChargeIntent
```

Результат является intent, а не командой. Engine и program не имеют доступа к
HA, Telegram, RD/ESP, Output, lease или safety actuator calls.

## Ownership

- `ChargeEngine` владеет только orchestration boundary и ссылками на domain
  profile/program.
- `ChargeProgram` владеет только pure evaluation policy.
- `ChargeState`, `Measurements`, `BatteryProfile` и `ChargeIntent` — data
  contracts.
- SafetyEngine и OutputAdapter остаются следующей внешней boundary и здесь не
  реализованы.

Registry не добавлялся: Minimum, Delta, Storage и Recovery ещё не реализованы.

## Migration path

1. Сопоставить текущие controller snapshots с `ChargeState`.
2. Создать read-only adapter для production measurements.
3. Переносить отдельные program decisions в `ChargeProgram` с parity tests.
4. Передавать полученный intent в существующую safety boundary.
5. Только после full regression и physical gates рассматривать controller
   migration.

Текущий controller, FSM и production runtime продолжают работать независимо;
legacy не подключён к новому engine.

## Verification

`tests/test_v3_charge_engine.py` проверяет BatteryProfile input, вызов программы,
возврат ChargeIntent, snapshot semantics и отсутствие integration imports.

Production, UI, actuator path, ESPHome/YAML и node 101 не изменялись.

# V3 START preflight boundary

## Назначение

Этот слой подготавливает решение по `START_CHARGE`, но не запускает заряд.
Он предназначен для read-only проверки перед отдельной миграцией START.

```text
UserIntent(START_CHARGE)
        |
        v
StartCommandHandler
        |
        v
StartPreflightService
        |
        +-- ownership
        +-- telemetry
        +-- profile / chemistry
        +-- recipe preview
        +-- target preview
        +-- safety preflight
        |
        v
ALLOW / DENY
```

## Контракты

`StartRequest` содержит профиль, ёмкость, идентификатор/химию АКБ, intent,
condition, оператора и контекст запроса.

`StartPreflightResult` содержит только результат анализа:

- `allowed`;
- `reasons`;
- ownership, telemetry и safety status;
- preview recipe;
- preview target.

Модели не содержат HA client, controller handle, session или physical object.

## Read-only ограничения

`StartPreflightService` разрешено читать live telemetry, ownership state,
controller target helpers и recipe/safety policy. Он не вызывает:

- `charge_controller.start()`;
- `_select_initial_auto_target()`;
- создание или изменение session/FSM;
- `HassClient` write methods;
- `safe_enable_output()`;
- setpoint или Output commands.

Вызов `StartCommandHandler.route()` пока не запускает preflight автоматически:
общий START intent остаётся `execution_intent_not_migrated`. Явный вызов
`preflight(StartRequest)` предназначен для shadow и последующей миграции.

## V2/V3 comparison

`compare_start_preflight()` принимает заранее снятый, неисполняющий V2 preview и
сравнивает его с `StartPreflightResult` по profile, chemistry, ownership,
telemetry, safety, recipe и target fields. Физический результат и mutation
состояния в comparison не участвуют.

## Проверенные deny cases

- `HANDS_OFF`;
- активная charge session;
- неизвестный профиль;
- stale/invalid telemetry;
- safety preflight denial;
- Output уже включён.

## Следующий этап

Перед миграцией START нужно закрыть parity report по реальным V2 capture-векторам,
затем отдельно перенести только orchestration через `StartCommandHandler`.
До этого production callback, controller, FSM, safety wrappers и physical path
остаются без изменений.


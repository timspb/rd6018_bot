# RD6018 V3 Charge Lifecycle Persistence Model

Статус: **CHARGE_LIFECYCLE_PERSISTENCE_READY**

Добавлен pure contract layer `application/charge_lifecycle/`.

## Snapshot

`ChargeLifecycleSnapshot` фиксирует:

- session/battery/program identity;
- current phase и phase start time;
- phase evidence;
- Delta и Hold state;
- safety state;
- telemetry timestamp;
- trace identity.

Snapshot immutable и не является runtime owner.

## Restore

- `START_NEW` — snapshot отсутствует;
- `RESUME_EXISTING` — snapshot имеет validated identity;
- `AMBIGUOUS` — legacy state существует, но identity отсутствует.

Без validated `session_id`/`trace_id` запрещены fake START и fake phase transition.

## Continuity

`LifecycleEvent` требует `session_id`, `trace_id` и timestamp. Validator проверяет identity consistency и монотонный порядок событий.

## Telemetry loss

`TelemetryContinuityGuard` сохраняет текущую phase при `STALE` или `MISSING`. Recovery может предложить переход только после `FRESH/RECOVERED` telemetry; guard не выполняет safety action.

## Tests

Проверены snapshot immutability, existing/legacy/new restore classification, HOLD/Delta state preservation, stale telemetry и event continuity. Persistence backend и production wiring не подключались.

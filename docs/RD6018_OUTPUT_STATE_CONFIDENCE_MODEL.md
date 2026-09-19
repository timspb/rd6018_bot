# RD6018 Output State Confidence Model

Статус: `IMPLEMENTED`

## Назначение

Модель отделяет возраст перехода состояния от свежести данных. `last_changed` у
HA switch показывает только момент последнего изменения состояния и не является
доказательством того, что источник перестал передавать данные.

## Authoritative sources

Для V2 output state используются:

- `Output State Code V2` — канонический OFF/ON readback (`0`/`1`);
- `Take Out V2` — safety/configuration indication; `true` блокирует разрешение;
- `Safety Modbus Age` — фактический возраст последнего Modbus обмена;
- `Protection Status Code` — код защиты, `0` означает normal;
- `safety_state`, если источник его предоставляет.

`switch.last_changed` не входит в authoritative freshness gate.

## Decision

`ALLOW` выдаётся только когда output code валиден, `Take Out V2` не указывает
опасное состояние, Modbus age не превышает 20 секунд, protection normal и
явный safety state (если присутствует) находится в нормальном состоянии.

`DENY` выдаётся при отсутствии/некорректности readback, stale Modbus, protection
fault, unsafe `Take Out` или safety fault. Fail-closed применяется до любых
дальнейших actuator действий.

## Проверка

Добавлены тесты:

- OFF с устаревшим `last_changed` и свежим Modbus → `ALLOW`;
- stale Modbus → `DENY`;
- protection fault → `DENY`.

Изменение не выполняет физических команд и не меняет ownership.

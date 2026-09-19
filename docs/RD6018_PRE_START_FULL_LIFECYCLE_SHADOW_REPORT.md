# RD6018 Pre-Start Full Lifecycle Shadow Capture

Статус: **PARTIAL_OBSERVATION**

## Pre-start gate result

Read-only pre-start check выполнен через сохранённую WinSCP-сессию node 101.
На момент проверки V2 уже был активен:

- state: `active`;
- profile: `Manual / Baic72`;
- phase: `MIX`;
- persisted output target: `17.5 V / 3.5 A`;
- `session_id`/`trace_id`: отсутствуют.

Условие `idle/no active session` не выполнено. Observer не может считать этот
момент началом нового цикла и не создаёт fake START.

## Observation metadata

- mode: V2 production owner / V3 read-only observer;
- source: node 101 persisted V2 state, with existing HA/ESP read-only source
  path available;
- start condition: **NOT SATISFIED**;
- timestamps: source `started_at` and `saved_at` сохранены как provenance;
- new observation id: не назначался, так как pre-start window не открыта.

## Required event chain

| Event | Result | Reason |
|---|---|---|
| START | NOT OBSERVED | observer начал после существующего active state |
| PREP | NOT OBSERVED | нет event source evidence |
| MAIN | NOT OBSERVED | нет event source evidence |
| DESULFATION | NOT OBSERVED | нет event source evidence |
| MIX | CURRENT STATE ONLY | phase observed, entry event не наблюдался |
| Delta start | NOT OBSERVED | отсутствует реальный event |
| Delta complete | NOT OBSERVED | отсутствует реальный event |
| HOLD | NOT OBSERVED | отсутствует реальный event |
| termination | NOT OBSERVED | отсутствует реальный event |
| DONE/STOP | NOT OBSERVED | отсутствует реальный event |

Ни одно событие не реконструировалось по persisted state, timestamps или
текущей телеметрии.

## Shadow parity

Для доступного current-state snapshot V3 может сравнить `Manual/Baic72/MIX`
и targets как read-only data. Это не является lifecycle parity: без observed
START и phase edges статусы событий остаются `UNKNOWN`.

## Safety boundary

Не выполнялись START/STOP, изменение уставок, lease operations, ownership
transfer, deployment, HA/ESPHome writes, RD commands или physical commands.

## Required next run

Нужен observer, запущенный до естественного нового V2 START при подтверждённом
idle state. Только после фактического наблюдения всей цепочки
`START → PREP/MAIN/... → Delta → HOLD → termination → DONE/STOP` статус можно
изменить на `FULL_LIFECYCLE_SHADOW_VALIDATED`.

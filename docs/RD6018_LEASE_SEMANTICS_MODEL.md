# RD6018 Lease Semantics Model

Статус: **LEASE_SEMANTICS_CONFIRMED**

Дата: 2026-09-16  
Режим: read-only audit; runtime, physical safety и ownership не изменялись.

## Canonical distinction

Lease — это не общий источник safety truth и не состояние локального RD6018. Он является
локальным edge dead-man для права bot-managed/remote automation продолжать управление
в режиме `managed_session`.

Отдельно существуют:

- `managed_session` — bot-managed ownership и 900s lease;
- `autonomous_mode` — явный persistent local/offline authority;
- intrinsic hardware safety — локальная защита RD/ESPHome, не зависящая от lease.

## 1. Lease ARM

Lease ARM разрешён только после того, как V2 runtime уже имеет активную bot-managed
сессию и проходит штатный START/turn-on boundary:

```text
bot-managed START
    -> active controller/session
    -> safety preflight
    -> edge lease ARM
    -> physical Output ON
```

Фактическая реализация `runtime_safety_strict.py` сначала требует
`controller_active`, затем вызывает `_arm_edge_lease()`. Сам edge дополнительно
требует свежие Modbus/readback evidence и начальное подтверждение Output OFF для
первичного ARM.

Следствие: lease не создаётся для простого чтения состояния, idle, локальной ручной
работы или произвольного уже включённого RD без принятия managed ownership.

## 2. Lease DISARM

Штатный DISARM выполняется после подтверждённого физического Output OFF. Канонические
триггеры:

- штатный `DONE`, если он завершает bot-managed программу и приводит Output к
  подтверждённому OFF;
- операторский STOP через bot;
- отмена bot-managed программы;
- аварийный/защитный путь после завершения проверки OFF.

`EdgeSafetyLease.disarm()` сам приостанавливает дальнейшие renewal calls, вызывает
существующий edge disarm entity и ждёт подтверждения `armed=false`, без quarantine и
с малым remaining TTL. Это не новый physical path.

Если Output OFF не подтверждён, lease не должен считаться успешно снятым: сохраняется
fail-safe состояние и uncertainty поверх физического состояния.

## 3. Где lease не применяется

Lease не является обязательным для:

- локальной ручной работы RD без bot-managed ownership;
- явного автономного RD режима без бота;
- отсутствия WiFi/HA/бота, когда нет активной `managed_session`.

`autonomous_mode` — отдельная explicit state transition, разрешённая только при
свежем прямом подтверждении Output OFF. Она не выводится из `HANDS_OFF`, отсутствия
lease, network loss или отсутствия session.

При валидном `autonomous_mode && !managed_session` ESPHome boot/lease path не запускает
managed lease quarantine и не требует renewal. Intrinsic safety при этом продолжает
работать локально.

## 4. Lease expiry

Истечение 900s TTL означает только потерю права managed automation продолжать
управление без нового разрешения/renewal.

В managed режиме edge dead-man переводит operation в containment (Output OFF/latched
trip согласно существующей edge policy). Это намеренная защита remote ownership, а не
изменение локальной safety философии.

В автономном режиме lease expiry неприменим: managed lease не вооружён и не является
источником local-mode shutdown. Network loss без `managed_session` также не является
lease fault.

## 5. Ownership and safety boundaries

| Событие | Lease effect | Physical safety effect |
|---|---|---|
| Bot START managed program | ARM/renew managed lease | существующий V2 safety preflight |
| Bot DONE/STOP/cancel + verified OFF | DISARM | существующий Output OFF verification |
| WiFi loss, managed session active | lease renewal no longer proven; expiry containment | edge dead-man may turn managed Output OFF |
| WiFi loss, no managed session | lease не применяется | local RD operation не выключается из-за lease |
| Autonomous local operation | lease не ARM/renew | intrinsic safety остаётся активной |
| Protection/overtemperature | не меняет lease semantics | local intrinsic protection может выключить Output |

Lease не заменяет:

- RD hardware protection;
- intrinsic overtemperature protection;
- telemetry/readback integrity checks;
- explicit emergency authority.

## 6. Evidence reviewed

- `runtime_safety_strict.py`: ARM только при `controller_active`; DISARM после verified OFF.
- `runtime_safety_v2.py`: renewal только для active Output/managed controller path.
- `edge_safety_lease.py`: TTL 900s, positive renewal ACK, serialized operations, verified DISARM.
- `esphome/packages/rd6018_safety_lease.yaml`: managed lease, separate persistent autonomous mode, expiry containment only for managed session.
- `esphome/packages/rd6018_intrinsic_safety.yaml`: local RD protection independent of WiFi, HA, bot and managed lease.
- `tests/test_esphome_safety_lease_contract.py`, `tests/test_esphome_intrinsic_safety_contract.py`,
  `tests/test_edge_autonomous_mode.py`: contract checks for separation and fail-closed behavior.

## 7. Explicit non-goals

- Lease не создаёт и не закрывает lifecycle identity сам по себе.
- Lease не является разрешением на произвольные setpoints.
- Lease не передаёт physical ownership V3.
- `HANDS_OFF` не равен autonomous и не является скрытым lease bypass.
- Этот документ не меняет существующие runtime paths.

## Final decision

**LEASE_SEMANTICS_CONFIRMED** — ARM привязан к bot-managed START, DISARM к штатному
завершению managed operation с verified OFF, local/autonomous operation отделена от
lease, а expiry ограничен managed automation и не заменяет physical safety.

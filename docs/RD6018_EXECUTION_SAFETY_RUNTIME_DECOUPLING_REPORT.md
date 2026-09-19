# RD6018 Execution Safety Runtime Decoupling — Workstream 2.2

Статический аудит и подготовка контрактов выполнены без изменения V2 runtime,
START/ACTIVE, ownership, HA/ESP команд и физического исполнения.

## Итог

| Blocker | Contract/inventory status | Production status |
|---|---|---|
| B3 actuator bypasses | `INVENTORIED` | `OPEN` — сохранённые V2 writers ещё не переведены через V3 dispatcher |
| B4 configuration conflicts | `EXPLICIT` | `OPEN` — unresolved registry намеренно не выбирает значение |
| B5 safety ownership | `CONTRACTED` | `OPEN` — V2/watchdog/lease/edge owners нельзя объединять без parity/bench gate |
| B6 import-time coupling | `INVENTORIED` | `OPEN` — V2 import-time construction сохранена намеренно |

Следовательно, архитектурный PASS и Stage 1 **не выдаются**. Контрактная часть
подготовлена, но требование “CLOSED” для production blockers несовместимо с
запретом менять V2 execution и ownership.

`ARCHITECTURE PASS`: NOT GRANTED.

## 1. Actuator path normalization

`application/actuator_reachability.py` строит read-only graph для:

- `OUTPUT_ON`, `OUTPUT_OFF`, `SET_VOLTAGE`, `SET_CURRENT`;
- `STOP`, `EMERGENCY_OFF`, `CONTAINMENT`.

Каждая запись содержит source/caller/owner/adapter/physical target,
production reachability и migration status. `dispatch_enabled` всегда `False`:
inventory не может вызвать controller, SafeOutput, HA, ESPHome или RD.

Целевой boundary:

```text
Domain -> ActuatorIntent -> ExecutionDispatcher -> Adapter -> Physical
```

Существующие V2 paths остаются compatibility paths и перечислены как bypass
относительно будущего V3 dispatcher. Они не скрыты и не перенаправлены.

## 2. Configuration authority normalization

Текущая `ConfigurationAuthority` проверяется на наличие owner/source/description,
type/default/validator для каждого зарегистрированного ключа. Источники по-прежнему
только читаются. `configuration_decision_registry.py` является реестром решений,
а не precedence layer.

Неразрешёнными остаются, в частности: watchdog 180/300 s, readback 5/10/15 s,
lease renewal, EFB 20/24 h, FLOODED/Custom schema, transport priority и
temperature policy. Автоматического выбора не сделано.

## 3. Safety ownership consolidation

`application/safety_ownership.py` добавляет только data-only coordinator:

```text
Detection/SafetySignal -> Safety Decision Authority -> ContainmentRequest
                                                   -> existing V2/edge boundary
```

Coordinator сохраняет trace/history и проверяет единый логический decision owner.
Он не отправляет OFF/STOP, не вызывает lease, SafeOutput, HA или ESPHome.
Watchdog, emergency stop, manual safety и ESPHome dead-man остаются действующими
защитами V2/edge и не заменяются этим контрактом.

## 4. Import graph and lifecycle

`application/lifecycle_inventory.py` фиксирует:

- `bot.py` как сохранённый V2 production composition;
- `runtime/v2_runtime.py` как legacy compatibility risk с import-time globals,
  workers и startup path;
- `bot_legacy.py` как rollback-only entrypoint;
- V3 lifecycle contracts как `CONTRACT_ONLY`/`SHADOW_ONLY` без startup.

V2 construction не переносилась и не переименовывалась: это обязательное
ограничение текущего workstream. Application modules проверяются на отсутствие
implicit `asyncio.run`, `HassClient` и ESPHome side effects.

## 5. Repeated WORKSTREAM 1 audit

Повторены static checks Workstream 1 и новые checks Workstream 2.2:

- actuator graph и bypass detection;
- configuration completeness/provenance presence;
- single logical safety decision owner;
- lifecycle/import isolation;
- report/invariant consistency.

Результат: Stage 0 behavior preserved; Stage 1–3 остаются `BLOCKED` до отдельной
approved migration с parity, exact ESPHome contract и bench validation.

## Restrictions confirmed

Не менялись V2 runtime, START, ACTIVE, HA control, ESP control, lease ownership,
physical output, production configuration values и production composition.

# RD6018 Legacy Ownership Separation — WORKSTREAM 3

Режим: contracts/inventory/static audit. Live ownership, V2 physical
execution, START/ACTIVE, HA/ESP control and lease ownership не менялись.

## Executive result

Workstream 3 сделал legacy boundaries и owners явными, но **Architecture PASS
не достигнут**. Это не является отказом от требований; production blockers нельзя
закрыть без тех изменений, которые текущий scope прямо запрещает.

| Blocker | R3 result | Explanation |
|---|---|---|
| B2 adapter boundary | `IMPROVED / ADAPTER-ONLY` | direct V3 imports проходят через named adapter; adapter всё ещё является V2 domain seam |
| B3 actuator ownership | `MAPPED / OPEN` | canonical map покрывает известные writers, но V2 physical paths не перенесены |
| B4 configuration authority | `INVENTORIED / OPEN` | registry содержит provenance/status, но unresolved values и runtime literals остаются |
| B5 safety ownership | `MAPPED / OPEN` | один logical decision owner описан, несколько physical execution writers сохранены |
| B6 lifecycle separation | `INVENTORIED / OPEN` | ApplicationComposition contract чистый, V2 import-time lifecycle не изменён |

## B2 — Adapter boundary hardening

`application/legacy_domain_adapter.py` — единственное место в `application/`,
которое импортирует `runtime.charge` и `runtime.charge.strategy`. V3-facing
application modules используют named adapter, а static test запрещает прямые
legacy-domain imports в остальных application modules.

Это закрывает прямой import bypass, но не делает V3 domain независимым от
legacy implementation. Полное закрытие требует parity-backed replacement of
the adapter and cannot be inferred from import isolation alone.

## B3 — Canonical actuator ownership map

`application/actuator_ownership_map.py` объединяет normalized inventory и
explicit direct paths:

- output ON/OFF;
- voltage/current setpoints;
- controller START/STOP;
- emergency OFF и containment;
- V2 runtime, SafeOutput, runtime safety, manual/diagnostic, startup/recovery,
  edge lease и ESP Direct transport.

Каждая запись содержит owner/source/path/adapter/physical target/migration
state. Direct legacy paths классифицированы как `KEEP`, `ADAPTER` или
`DEPRECATE`; они не перенаправляются и не исполняются картой.

Целевой graph остаётся:

```text
Domain -> ActuatorIntent -> ExecutionDispatcher -> Adapter -> Physical
```

Production bypasses остаются открытыми намеренно: их устранение изменило бы
V2 execution/ownership.

## B4 — Configuration authority inventory

`application/configuration_registry.py` строит единый read-only inventory поверх
`ConfigurationAuthority` и unresolved decision registry. Каждая запись содержит
name/section/owner/type/default/validator/provenance/migration status.

Не выбранные автоматически решения остаются `UNRESOLVED` или
`MIGRATION_REQUIRED`: EFB Mix 20/24 h, watchdog, readback windows, lease
renewal, temperature policy, transport priority, FLOODED и Custom schema.

Registry не является precedence switch и не меняет effective V2 configuration.
Поэтому B4 observability улучшена, но authority closure не достигнута.

## B5 — Safety ownership model

`application/safety_ownership_map.py` разделяет:

```text
Detection -> Safety Decision Authority -> existing V2/edge execution
```

Карта покрывает watchdog, telemetry loss, lease loss, manual stop, emergency
stop и readback failure. Static tests подтверждают один logical decision owner
и одновременно обнаруживают несколько сохранённых execution writers. Это
необходимо для безопасности текущего V2/ESPHome контракта; writers не
объединялись и не отключались.

## B6 — Lifecycle inventory

`application/lifecycle_inventory.py` и import tests подтверждают отсутствие
runtime start/physical client construction в application contract layer и
фиксируют единственного intended V3 composition owner.

Одновременно production inventory сохраняет факты:

- `bot.py` — V2 production composition;
- `runtime/v2_runtime.py` — import-time Telegram/HA globals и workers;
- `bot_legacy.py` — rollback entrypoint;
- V3 composition — shadow-only.

Удаление этих side effects потребует отдельного runtime migration и restart/
rollback evidence, поэтому B6 не закрыт в текущем scope.

## Acceptance

- B2 adapter isolated: **partial / adapter-only PASS**;
- B3 actuator ownership mapped: **PASS as inventory, production closure OPEN**;
- B4 configuration authority complete as inventory: **PASS as inventory, effective authority OPEN**;
- B5 safety ownership explicit: **PASS as model, writer consolidation OPEN**;
- B6 lifecycle isolated: **PASS for V3 contracts, V2 production OPEN**.

**Architecture PASS: NOT GRANTED.**

Stage 0 remains preserved and PASS. Stage 1, decision cutover, execution
cutover and physical migration remain disabled.

## Verification

- Workstream 3 static tests: adapter/import isolation, actuator coverage,
  configuration provenance/drift and safety writer detection;
- existing Workstream 1/2 tests remain required;
- no physical command, HA/ESP write, lease change or runtime ownership change.

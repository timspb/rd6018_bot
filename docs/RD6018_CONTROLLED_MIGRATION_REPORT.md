# RD6018 Controlled Migration & Legacy Elimination

## Scope and safety boundary

Создан изолированный pure `v3_core` для controlled migration preparation.
Он не импортирует V2, `runtime`, HA, ESPHome, legacy state или physical
connectors. Его execution adapter — только shadow/dry-run и не выполняет
команды.

Production V2 runtime, physical execution, HA/ESP/lease ownership и Stage 1 не
изменялись. Поэтому этот документ фиксирует подготовленный migration slice,
а не утверждает физический takeover.

## Part 1 — V3 pure core

Добавлены:

- `v3_core/contracts.py` — standalone telemetry, intent, safety, decision и
  execution contracts;
- `v3_core/domain.py` — pure domain decision engine;
- `v3_core/safety.py` — canonical V3 safety decision model;
- `v3_core/configuration.py` — typed V3 authority contract;
- `v3_core/composition.py` — единственный standalone composition root;
- `v3_core/execution.py` — dispatcher + non-physical shadow adapter.

Static tests запрещают legacy/infrastructure imports из `v3_core`.

## Part 2 — Actuator migration status

Целевой путь подготовлен:

```text
V3 Domain -> V3 ActuatorIntent -> V3 ExecutionDispatcher -> V3 Adapter -> Physical target
```

В текущем изменении physical adapter не подключён. Поэтому:

- contract path: `PASS`;
- shadow dispatch: `PASS`;
- physical parity: `BLOCKED`;
- V2 path removal: `NOT PERFORMED`.

Нельзя удалять старые physical paths до exact adapter parity, readback,
rollback и ESPHome bench validation.

## Part 3 — Safety migration status

V3 safety flow разделён:

```text
Detection -> V3 Safety Decision -> Containment Intent -> V3 Execution Boundary
```

V2 safety используется только как behavior/parity reference в рамках текущего
изменения; production writers не перенаправлены. Safe physical containment
остаётся вне этого pure-core slice.

Status: model/shadow `PASS`, production safety migration `BLOCKED`.

## Part 4 — Configuration migration status

V3 core имеет typed authority schema и отвергает неизвестные параметры.
Полная migration всех проектных значений не выполнена: текущие YAML/Python/
env/runtime/persisted sources ещё содержат конфликты и не могут быть удалены
без утверждённых parity decisions.

Status: core contract `PASS`, canonical production authority `BLOCKED`.

## Part 5 — Runtime migration status

`V3Composition.standalone()` является единственным composition root внутри
`v3_core`; конструкция не запускает workers, network, persistence или hardware.

Production `bot.py`/V2 runtime не изменялись и не подключались к V3 core.
Полноценное V3 runtime takeover требует отдельного approved migration,
restart/rollback evidence и physical gate.

Status: standalone core `PASS`, production runtime replacement `BLOCKED`.

## Validation

- V3 core forbidden-import tests;
- standalone composition test;
- shadow actuator dispatch test;
- canonical safety non-physical test;
- configuration unknown-key rejection.

## Acceptance

| Criterion | Result |
|---|---|
| no V2 imports in V3 core | PASS |
| no legacy execution ownership in V3 core | PASS |
| one V3 shadow actuator path | PASS |
| one V3 logical safety owner | PASS for pure core |
| one V3 configuration contract | PASS for pure core |
| one production lifecycle owner | BLOCKED until runtime cutover |
| legacy physical path elimination | BLOCKED until physical parity/bench gate |
| Architecture PASS | NOT GRANTED |

Stage 1 and physical migration were not performed.

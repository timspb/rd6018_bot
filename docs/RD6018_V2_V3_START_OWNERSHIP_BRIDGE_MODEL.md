# RD6018 V2/V3 START Ownership Bridge — WORKSTREAM 87

Статус: `START_OWNERSHIP_BRIDGE_READY`

Документ является проектом перехода. Runtime и ownership не изменяются.

## 1. Текущее состояние

```text
v2_bot_ui._start_profile()
    |
    +--> charge_controller.start(...)
    +--> HassClient.set_voltage/set_current/turn_on
    |
    v
V2 transaction / SafeOutput boundary
    |
    v
RD6018 physical output
```

Текущий physical owner — V2 production path: `DiagnosticProductionChargeControllerV2`
совместно с V2 transactional `HassClient`/`SafeOutputCoordinator` boundary. Рядом
существуют отдельные V2 manual и safety paths; этот bridge их не переназначает.

## 2. Целевая граница

```text
Operator START
    |
    v
V3 StartOrchestration / единственный StartAuthority
    |
    +--> session_id + trace_id + graph_session_id
    +--> SessionStarted (lifecycle fact)
    +--> ExecutionIntent
    |
    v
approval / safety gate
    |
    v
existing V2 physical owner (during bridge)
```

На bridge-этапе V3 получает право сформировать canonical intent и identity,
но не получает physical ownership. `PhysicalExecutionRequest` должен быть
создан только после отдельного явно включённого режима; в текущем design-only
режиме он не создаётся и никуда не отправляется.

## 3. Single StartAuthority

`StartOrchestration` — единственная точка, где будущий V3 START может пройти
проверку и получить lifecycle identity. UI не вызывает `charge_controller`, HA,
ESPHome или RD напрямую. V2 START остаётся действующим до отдельного cutover.

## 4. Защита от двойного START

До внедрения требуется атомарный bridge registry с состояниями:

- `V2_ACTIVE` — текущий V2 START path является единственным physical path;
- `V3_SHADOW` — V3 только наблюдает/считает, не запускает V2;
- `V3_HANDOFF_PENDING` — подготовка handoff, physical action запрещён;
- `V2_ROLLBACK` — возврат к V2.

Для каждого request используется idempotency key, равный `request_id`; для
каждой session допускается не более одного accepted START. Повторный запрос
должен возвращать существующий decision/identity, а не повторять START.
Параллельные V2 и V3 accepted-start решения запрещаются conflict guard.

## 5. Identity handoff

Передаваемые поля:

| Поле | Создаёт | Передаётся | Правило |
|---|---|---|---|
| `session_id` | StartAuthority | lifecycle, evidence, future V2 handoff | immutable на сессию |
| `trace_id` | StartAuthority | audit, diagnostics, intent | immutable на request chain |
| `graph_session_id` | StartAuthority | UI/graph layer | не является physical proof |
| `program_id` | StartRequest/Program authority | lifecycle, intent provenance | canonical ID, без alias logic |

`SessionStarted` означает только lifecycle creation и не доказывает `Output ON`.
Физический факт подтверждается существующим V2 readback/verification path.

## 6. Rollback

Rollback owner остаётся V2. При duplicate-start conflict, failed approval,
identity mismatch, stale safety/evidence или отсутствии V2 acknowledgement:

1. не отправлять physical request;
2. сохранить V3 decision/audit evidence;
3. вернуть bridge в `V2_ACTIVE`/`V2_ROLLBACK`;
4. продолжить только существующим V2 path.

Rollback не создаёт fake START и не переписывает legacy session history.

## 7. Запреты до отдельного cutover

- не менять `v2_bot_ui._start_profile()`;
- не подключать V3 executor к HA/ESPHome/RD;
- не передавать V3 lease или physical ownership;
- не выполнять реальные START/STOP;
- не считать lifecycle event подтверждением физического output.


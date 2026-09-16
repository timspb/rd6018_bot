# RD6018 composition root model (Phase 6.0)

Статус: contracts + analysis only. Production runtime и текущая V2
инициализация не изменены.

## Current production inventory

Текущий production entrypoint — `bot.py`, который импортирует
`runtime.v2_runtime` и последовательно вызывает `install_*` wrappers. Основные
слои текущей сборки:

- `runtime/v2_runtime.py` — историческая V2 runtime/bootstrap surface с
  Telegram, HA client, controller и module globals;
- `v2_bootstrap.py` — V2 controller/safety/UI composition и V3 START dry-run
  boundary wiring;
- `v2_startup.py` и `runtime/v2_startup_recovery.py` — startup/transaction/
  recovery paths;
- многочисленные top-level installers — compatibility, ownership, UI,
  watchdog, persistence и diagnostics wrappers;
- `bot_legacy.py` — rollback-only preserved entrypoint, не production root.

Следовательно, текущая система ещё имеет распределённую историческую сборку.
Эта фаза не удаляет и не переписывает её.

## Target `ApplicationComposition`

`application.composition_contract.ApplicationComposition` фиксирует единую
будущую точку сборки:

```text
ApplicationComposition
├── domain
├── application
├── infrastructure
├── ui
└── persistence
```

Composition root отвечает только за создание объектов и соединение портов:

1. создать pure domain objects;
2. создать application services/use cases;
3. выбрать и подключить infrastructure adapters;
4. подключить UI adapter;
5. подключить persistence adapter;
6. передать готовый immutable graph в startup runner.

## Forbidden composition-root responsibilities

Composition root не содержит:

- charge FSM, recipe/strategy/safety logic или transition decisions;
- Telegram handlers/callback logic;
- HA/ESP calls или transport retry logic;
- ESPHome lease/watchdog behavior;
- physical commands, actuator calls или output ownership;
- persistence policy/SQL/JSON mutation logic;
- second bootstrap path or hidden module-global initialization.

It may receive a prebuilt owner/adapter and connect it, but it must not become
the owner of the behavior.

## Layer responsibilities

| Layer | Creates/connects | Must not own |
|---|---|---|
| Domain | states, profiles, strategies, domain safety | I/O, persistence, UI, transport |
| Application | intents, preflight, use cases, orchestration ports | physical implementation or Telegram transport |
| Infrastructure | HA/ESP/RD adapters, lease, stores, telemetry sources | charge decisions or UI semantics |
| UI adapter | Telegram commands, dashboard, feedback | FSM, safety, HA/ESP, physical calls |
| Persistence | repositories/read-write adapters | actuator authority or restart authorization |

## Single-root invariant

There is one authoritative `ApplicationComposition` for a running process and
one startup handoff. Rollback `bot_legacy.py` remains a separate explicitly
selected compatibility entrypoint, not a second production root. Historical
installer functions may remain until migration, but future code must not add a
new independent bootstrap or module-global owner.

## Bootstrap purity contract

The current `v2_bootstrap.py` is classified as transitional composition. It may
connect existing V2 owners and V3 dry-run ports, but it must not acquire charge
logic. Static checks therefore reject phase constants, strategy transitions,
physical call sites and direct domain algorithms in the bootstrap module.

## Migration boundary

Phase 6.0 does not switch `bot.py`, does not change startup order, does not
remove installers, and does not wire `ApplicationComposition`. A later phase
must first inventory every installer and prove equivalent ownership before one
root replaces the distributed V2 bootstrap.

# V3 Legacy Runtime Inventory

Дата фиксации: 2026-09-14

Этот документ фиксирует фактический production composition на ветке
`codex/v3-runtime-consolidation`. Он не является разрешением на включение ACTIVE
или на изменение физического контура.

## Production entrypoint

```text
python bot.py
  |
  +-- import bot_legacy as _legacy
  +-- install_v2(_legacy)
  +-- install_*(_legacy)          # V2 safety/ownership/UI decorators
  +-- _legacy.operator_interface  # V3 read boundary
  +-- _legacy.main()              # один polling owner
```

`bot.py` не запускает `bot_legacy.py` как отдельный процесс: импорт выполняется
внутри одного процесса, а `asyncio.run()` находится только в `bot.py` при обычном
production запуске. При этом production runtime всё ещё импортирует legacy-модуль
и использует его глобальное состояние.

## Telegram lifecycle inventory

| Объект | Файл/функция | Статус | Действие |
|---|---|---|---|
| `Bot(...)` | `bot_legacy.py:77` | один экземпляр в текущем процессе | MIGRATE в Telegram adapter |
| `Dispatcher()` | `bot_legacy.py:78` | один экземпляр в текущем процессе | MIGRATE в Telegram adapter |
| `dp.start_polling(bot)` | `bot_legacy.py:4249` | единственный найденный polling call | KEEP до завершения lifecycle migration |
| `bot.main()` | `bot.py:336` | production asyncio entrypoint | KEEP, сократить до composition/lifecycle |
| `bot_legacy.main()` | `bot_legacy.py:4155` | фактическая сборка legacy runtime | MIGRATE по фазам; не запускать отдельно |

## Runtime ownership inventory

| Область | Текущий владелец | Файл/функция | Классификация |
|---|---|---|---|
| ChargeController/FSM | V2 controller | `v2_bootstrap.py:install_v2`, `diagnostic_controller.py` | KEEP до parity |
| Session lifecycle | `ProductionManualSessionManager` | `v2_bootstrap.py:install_v2` | KEEP; затем MIGRATE adapter-ом |
| Safety/output | V2 safety stack | `v2_bootstrap.py`, `v2_startup.py` | KEEP до physical parity |
| Startup recovery | V2 recovery composition | `bot.py:_replay_deferred_startup_restore` | MIGRATE в runtime service после полного audit |
| Telegram command/callback handlers | legacy router | `bot_legacy.py:2511-4074` | MIGRATE по одному bounded path |
| Dashboard transport | legacy functions + V3 decorators | `bot_legacy.py:1845-1980`, installers | MIGRATE read/presentation; renderer уже data-only |
| V3 START boundary | V3 route/preflight/port | `application/*`, wired in `v2_bootstrap.py` | KEEP; ACTIVE remains gated |

## Direct production references from `bot.py`

| Reference | Why it exists | Classification |
|---|---|---|
| `_legacy.charge_controller` | deferred startup restore | MIGRATE after restart/containment parity |
| `_legacy.hass` | deferred startup read/write and verified recovery | KEEP behind existing safety owner; later MIGRATE |
| `_legacy._operator_pause_active()` | durable operator pause guard | MIGRATE with session service |
| `_legacy._restore_allows_auto_enable()` | terminal restore guard | KEEP until replacement is proven |
| `_legacy._apply_phase_protection()` | startup restore protection | KEEP with V2 safety owner |
| `_legacy.main` | current Telegram/runtime lifecycle | MIGRATE in Phase 1 |

## Start routes

Current authoritative saved-battery route:

```text
Telegram callback `v2_battery_start`
  -> `_v2_battery_start_route` (`v2_bootstrap.py`)
  -> `ProductionStartRouteAdapter`
  -> validator/preflight/plan
  -> `ProductionStartExecutionPort` (DRY_RUN by default)
```

The V2 transaction owner remains `start_profile_transactional()` through the
existing adapter and is not duplicated. Legacy direct helpers remain present for
rollback/compatibility and are not evidence of a second polling process. They are
classified as `QUARANTINE` until route and parity tests permit removal.

## Background tasks registered by legacy main

`bot_legacy.main()` registers `data_logger`, `charge_monitor`,
`soft_watchdog_loop`, and `watchdog_loop`, plus shutdown cleanup. These tasks may
touch telemetry, persistence, ownership, safety, and output. They must be moved
behind explicit runtime lifecycle interfaces before `bot_legacy.py` can be removed.

## Files by action

### KEEP for now

- `v2_bootstrap.py`
- `v2_startup.py`
- V2 controller, safety, ownership, and physical adapters
- `application/` V3 contracts and gated ports

### MIGRATE

- Telegram bot/dispatcher construction and lifecycle in `bot_legacy.py`
- command/callback registration in `bot_legacy.py`
- legacy global runtime state used by UI and background tasks
- startup recovery functions currently in `bot.py`

### QUARANTINE

- `bot_legacy.py` direct entrypoint (`if __name__ == "__main__"`)
- legacy direct START helpers not reachable from the authoritative production
  route
- old UI compatibility handlers after their replacement has parity coverage

### REMOVE only after gates

- `bot_legacy.py` production import
- direct legacy entrypoint and duplicate compatibility surfaces

## Phase 0 gate result

- one `Bot` construction found;
- one `Dispatcher` construction found;
- one `start_polling` call found;
- one production `asyncio.run(main())` path found;
- ACTIVE remains fail-closed by default;
- physical execution was not invoked;
- legacy production import is confirmed and is the next migration blocker.

## Phase 1 progress

- `telegram/runtime.py` owns construction of the Bot/Dispatcher/Router bundle;
- `telegram/runtime.py` owns command registration, polling invocation, and Telegram
  session close;
- `bot_legacy.py` still owns handler definitions, startup recovery, background task
  creation, and V2 domain state;
- no second polling owner was introduced;
- no ACTIVE or physical execution was invoked.

The remaining Phase 1 work is lifecycle extraction around the existing handler and
V2 task callbacks. It must not move controller, session, safety, or physical
ownership into the Telegram adapter.

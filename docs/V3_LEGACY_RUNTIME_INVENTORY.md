# V3 Legacy Runtime Inventory

Дата фиксации: 2026-09-14

Этот документ фиксирует фактический production composition на ветке
`codex/v3-runtime-consolidation`. Он не является разрешением на включение ACTIVE
или на изменение физического контура.

## Production entrypoint

```text
python bot.py
  |
  +-- import runtime.v2_runtime as _legacy
  +-- install_v2(_legacy)
  +-- install_*(_legacy)          # V2 safety/ownership/UI decorators
  +-- _legacy.operator_interface  # V3 read boundary
  +-- _legacy.main()              # один polling owner
```

`bot.py` импортирует `runtime.v2_runtime` внутри одного процесса. Историческое
имя `bot_legacy.py` оставлено только как rollback shim и не входит в production
import graph.

## Telegram lifecycle inventory

| Объект | Файл/функция | Статус | Действие |
|---|---|---|---|
| `Bot(...)` | `runtime/v2_runtime.py:77` | один экземпляр в текущем процессе | MIGRATE в Telegram adapter |
| `Dispatcher()` | `runtime/v2_runtime.py:78` | один экземпляр в текущем процессе | MIGRATE в Telegram adapter |
| `dp.start_polling(bot)` | `runtime/v2_runtime.py:4249` | единственный найденный polling call | KEEP до завершения lifecycle migration |
| `bot.main()` | `bot.py:336` | production asyncio entrypoint | KEEP, сократить до composition/lifecycle |
| `v2_runtime.main()` | `runtime/v2_runtime.py:4155` | фактическая сборка V2 runtime | MIGRATE по фазам; не запускать отдельно |

## Runtime ownership inventory

| Область | Текущий владелец | Файл/функция | Классификация |
|---|---|---|---|
| ChargeController/FSM | V2 controller | `v2_bootstrap.py:install_v2`, `diagnostic_controller.py` | KEEP до parity |
| Session lifecycle | `ProductionManualSessionManager` | `v2_bootstrap.py:install_v2` | KEEP; затем MIGRATE adapter-ом |
| Safety/output | V2 safety stack | `v2_bootstrap.py`, `v2_startup.py` | KEEP до physical parity |
| Startup recovery | V2 recovery composition | `runtime/v2_startup_recovery.py:V2StartupRecovery` | KEEP as V2 delegated owner |
| Telegram command/callback handlers | preserved V2 router | `runtime/v2_runtime.py:2511-4074` | MIGRATE по одному bounded path |
| Dashboard transport | V2 functions + V3 decorators | `runtime/v2_runtime.py:1845-1980`, installers | MIGRATE read/presentation; renderer уже data-only |
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

The quick-profile capacity continuation now enters the same route when V3 is
composed. Its old mutating body remains only as a no-V3 rollback fallback and is
not used by the production composition.

The V2 transaction owner remains `start_profile_transactional()` through the
existing adapter and is not duplicated. Legacy direct helpers remain present for
rollback/compatibility and are not evidence of a second polling process. They are
classified as `QUARANTINE` until route and parity tests permit removal.

## Background tasks registered by legacy main

`v2_runtime.main()` registers `data_logger`, `charge_monitor`,
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

- Telegram bot/dispatcher construction in `telegram/runtime.py`; lifecycle in
  `runtime/v2_lifecycle.py`
- handler definitions remain in `runtime/v2_runtime.py`; registration orchestration
  is in `runtime/v2_lifecycle.py`
- legacy global runtime state used by UI and background tasks
- startup recovery functions currently in `bot.py`

### QUARANTINE

- rollback shim `bot_legacy.py` direct entrypoint (`if __name__ == "__main__"`)
- legacy direct START helpers not reachable from the authoritative production
  route
- old UI compatibility handlers after their replacement has parity coverage

### REMOVE only after gates

- historical `bot_legacy.py` production import
- direct legacy entrypoint and duplicate compatibility surfaces

## Phase 0 gate result

- one `Bot` construction found;
- one `Dispatcher` construction found;
- one `start_polling` call found;
- one production `asyncio.run(main())` path found;
- ACTIVE remains fail-closed by default;
- physical execution was not invoked;
- legacy module is quarantined from production imports; V2 runtime ownership is
  retained under the neutral `runtime.v2_runtime` name until further extraction.

## Phase 1 progress

- `telegram/runtime.py` owns construction of the Bot/Dispatcher/Router bundle;
- `telegram/runtime.py` owns polling invocation and Telegram transport session close;
- `runtime/v2_lifecycle.py` owns V2 startup/shutdown sequencing and command
  registration orchestration;
- `runtime/background.py` owns task creation while legacy callbacks remain the
  domain owners;
- `runtime/v2_startup_recovery.py` owns the production startup-recovery orchestration;
- `runtime/v2_runtime.py` still owns handler definitions, callback bodies, and V2
  domain state;
- no second polling owner was introduced;
- no ACTIVE or physical execution was invoked.

The remaining Phase 1 work is lifecycle extraction around the existing handler and
V2 task callbacks. It must not move controller, session, safety, or physical
ownership into the Telegram adapter.

The production entrypoint now delegates startup authority recovery and deferred
restore to `V2StartupRecovery`. The original helper functions remain in `bot.py` as
temporary compatibility seams for rollback-oriented tests and must be removed only
after their callers and source-contract tests are migrated.

## Verification after Phase 1 increments

- `test_v3_legacy_inventory.py`: PASS;
- `test_telegram_runtime_adapter.py`: PASS;
- `test_v2_entrypoint.py`: PASS;
- `test_operator_hmi.py`: PASS for current semantic HMI tests;
- `test_operator_actions.py`: PASS;
- `compileall`: PASS;
- full local suite: 1412 tests, one Windows-only AF_UNIX bench-control error and
  one legacy compatibility-builder expectation remain; no new V3 transport failure
  was observed;
- host 101 was not deployed or started during this migration work.

# V3 Runtime Ownership Map

Статус: Phase 1 — forensic inventory, без реализации миграции

Baseline:

```text
28d7f83dffa3f0aa9929b5fcc5246f704b830e94
```

Ветка:

```text
codex/v3-runtime-consolidation
```

Инвентарь выполнен по текущему runtime на baseline и последующей
documentation-only фиксации Phase 0. Этот документ не меняет ownership,
controller, UI, safety, ESPHome или production.

## 1. Lifecycle ownership

| Responsibility | Current owner | File/function | Risk | Target owner |
|---|---|---|---|---|
| Process entry | V2 shim | `bot.py` / module entrypoint | module aliasing | `RuntimeApp` |
| V2 startup | V2 shim | `bot.py:main` | startup split from legacy | `RuntimeApp.lifecycle` |
| Storage init | V2 bootstrap | `bot.py:main` → `init_v2_storage` | ordering implicit | `RuntimeApp.persistence` |
| Authority reconciliation | startup gate | `bot.py:main` → `reconcile_startup_authority` | parallel startup race surface | `RuntimeApp.startup` |
| Physical-test listener | bench adapter | `bot.py:main` → `_physical_test_control.start/stop` | lifecycle coupled to shim | isolated `BenchAdapter` |
| Telegram startup/polling | legacy runtime | `bot_legacy.py:main` | second lifecycle owner | `RuntimeApp.telegram` |
| Telegram shutdown | legacy runtime | `bot_legacy.py:on_shutdown` registered by `dp.shutdown` | shutdown ownership split | `RuntimeApp.lifecycle` |
| Periodic DB cleanup | legacy runtime | `bot_legacy.py:main` → `_periodic_db_cleanup` | unsupervised task | `RuntimeApp.task_registry` |
| Data logger / charge monitor | legacy runtime | `bot_legacy.py:main` → `data_logger`, `charge_monitor` | loops read mixed globals | `RuntimeApp.telemetry` |
| Software watchdog loops | legacy runtime | `bot_legacy.py:main` → `soft_watchdog_loop`, `watchdog_loop` | multiple containment paths | `SafetyEngine` |
| Deferred dashboard refresh/notifications | legacy handlers | `bot_legacy.py` via `asyncio.create_task` | task lifetime not centralized | `RuntimeApp.task_registry` |
| Manual session loop | Manual manager | `manual_mode.py:ManualSessionManager.start` | manager owns task directly | `ChargeController`/task registry |

Факт: `bot.py` вызывает legacy `main()`, а `bot_legacy.py` регистрирует polling
и фоновые loops. Это два lifecycle слоя, хотя процесс один.

## 2. Dependency creation ownership

| Object | Created in | Consumed by | Scope | Target owner |
|---|---|---|---|---|
| Telegram `Bot` | `bot_legacy.py` module globals | legacy handlers, notification paths, polling | module global | `TelegramAdapter` |
| `Dispatcher` | `bot_legacy.py` module globals | all routers and polling | module global | `TelegramUI` |
| `Router` | `bot_legacy.py` module globals | legacy and installed handlers | module global, mutated by installers | `TelegramUI` |
| `HassClient` | `bot_legacy.py` module globals | controller, managers, handlers, guards | module global, methods wrapped | `HAAdapter` |
| Initial `ChargeControllerV2` | `bot_legacy.py` module globals | replaced by `v2_bootstrap.install_v2` | module global | `ChargeController` factory |
| Production controller | `v2_bootstrap.install_v2` | `bot_legacy`, V2 UI, startup/recovery | module global on legacy module | `RuntimeApp.controller` |
| Manual manager | `v2_bootstrap.install_v2` | manual handlers, monitor, startup | module global on legacy module | `RuntimeApp.manual_session` |
| V2 safety guard | `runtime_safety_v2.install_v2_runtime_safety` | Hass/controller and ownership guards | attached to app | `SafetyEngine` |
| Safe output coordinator | `runtime_safety_v2` / `safe_output` | HA and controller paths | attached safety boundary | `SafetyEngine.output` |
| Control-mode manager | `rd_control_mode.install_rd_control_mode` | ownership wrappers/UI | module global on legacy module | `OwnershipEngine` |
| Autonomous coordinator | `rd_autonomous_mode.install_rd_autonomous_mode` | autonomous UI and edge transitions | module global on legacy module | `OwnershipEngine.autonomous` |
| Startup gate | `rd_startup_authority.install_rd_startup_authority_gate` | wrappers and reconciliation | module global on legacy module | `RuntimeApp.startup` |
| Physical-test control | `physical_test_control.install_physical_test_control` | bench-only extensions | module global on legacy module | isolated `BenchAdapter` |
| DB connection | `database.get_db` | database functions | module-level cached connection | `Persistence` |

Скрытая композиция: installers заменяют методы `app.hass`, controller methods,
legacy globals и module functions. `bot.py` затем aliases `sys.modules[__name__]`
к `_legacy`, поэтому импортный identity и monkeypatch semantics являются частью
текущего runtime behavior.

## 3. State write inventory

| State | Writer | File/function | Current owner | Target owner |
|---|---|---|---|---|
| `current_stage`, active flags, chemistry/counters | legacy controller methods | `charge_logic.py` / `ChargeController.start`, `stop`, `process` | `ChargeController` base | `ChargeState` + controller |
| V2 transition evidence/decision state | V2 controller | `charge_controller_v2.py`, `production_controller.py` | subclass fields and decision helpers | `ChargeController` |
| diagnostic context/assessment | diagnostic controller | `diagnostic_controller.py` / `update_diagnostic_context` | `DiagnosticProductionChargeControllerV2` | `DiagnosticState` |
| manual lifecycle/timers | Manual manager | `manual_mode.py`, `manual_runtime_v2.py` / `start`, `stop`, `_run` | Manual manager | `ManualState` under app |
| setpoint cache | controller + polling | `charge_logic.py` fields and `bot_legacy.py` telemetry path | split controller/legacy globals | `ChargeState` snapshot |
| operator pause | legacy globals/file | `bot_legacy.py` pause helpers and JSON persistence | legacy module | `SessionPersistence` |
| charge continuation | controller | `charge_logic.py:_save_session`, `try_restore_session`; V2 overrides | controller plus restore callers | `SessionPersistence` |
| diagnostic journal | diagnostic persistence | `diagnostic_persistence.py:_persist` | journal object | `DiagnosticPersistence` |
| ownership mode | control manager | `rd_control_mode.py:_write_mode` | `RdControlModeManager` | `OwnershipEngine` |
| edge AUTONOMOUS observation | control/autonomous managers | `rd_control_mode.py:_observe_edge_mode`, `rd_autonomous_mode.py` | split manager/coordinator | `OwnershipEngine` |
| DB charge records/history | database functions | `database.py` | module-level DB functions | `Persistence` |

### Double-owner findings

- Stage/transition behavior has two intentional layers: V2 decision/transition
  code and the legacy `ChargeController` safety/mechanics scaffold. This is the
  principal migration conflict; it is not resolved by renaming classes.
- Restore is invoked from several legacy paths (`bot_legacy.py`) and is guarded
  and replayed by `rd_startup_authority.py`/`bot.py`. The startup gate is the
  authority boundary, but restore intent is currently distributed.
- HA actuator methods are wrapped successively by safety, control-mode and
  startup installers. The wrappers are boundaries, not independent physical
  owners, but their order is behaviorally significant.
- Manual state and charge-controller state are separate by design; they must not
  be collapsed without preserving the explicit Manual authority contract.

Все перечисленные записи имеют найденного owner; unresolved ownership относится
к композиционному split, а не к неизвестному файлу.

## 4. Actuator ownership

### Common transactional path

```text
intent/transition
  -> controller or explicit manager
  -> SafetySupervisor / V2RuntimeSafetyGuard
  -> SafeOutputCoordinator / HassClient safety wrappers
  -> HassClient._switch_service / HA entity
  -> RD6018 edge
```

Реальные базовые команды определены в `hass_api.py`: `turn_on`, `turn_off`,
`set_voltage`, `set_current`. Их публичные вызовы дополнительно обёрнуты
`runtime_safety.py`, `runtime_safety_v2.py`, `rd_control_mode.py` и
`rd_startup_authority.py`.

| Path | Intent source | Safety check | Physical caller | Owner now |
|---|---|---|---|---|
| Automatic stage transition | controller tick | V2 safety + readback | legacy tick action executor | V2 controller with legacy scaffold |
| Manual start | Telegram Manual handler | `ProductionManualSessionManager` + safe enable | `manual_runtime_v2.py`/Hass | Manual manager |
| Explicit managed stop | operator callback | session-bound stop + verified OFF | `operator_managed_stop.py` | Managed-stop transaction |
| HANDS_OFF output OFF | ownership operator action | verified OFF | `rd_control_mode.py` | `RdControlModeManager` |
| AUTONOMOUS entry/exit | autonomous callback | edge ACK, fresh OFF, ownership gate | `rd_autonomous_mode.py` | `RdAutonomousModeCoordinator` |
| Startup restore | persisted session | startup authority + safe enable | `bot.py`/`bot_legacy.py` | startup gate + controller |
| Safety containment | telemetry/lease/watchdog | fail-closed guard | safety wrappers | `SafetyEngine` |

`bot_legacy.py` всё ещё содержит прямые вызовы `hass.turn_on/turn_off` и
setpoint methods. Они не являются свободными bypass в production composition,
поскольку поздние wrappers перехватывают методы, но это migration risk и
кандидат на устранение только с regression evidence.

## 5. Telegram/UI ownership

### Commands и presentation

- Базовые commands, dashboard and legacy panels: `bot_legacy.py`.
- V2 program/battery UI: `v2_bot_ui.py` через `v2_bootstrap.py`.
- Manual input/context: `manual_text_v2.py`, `manual_context_v2.py`.
- Mix UI: `v2_mix_mode.py`.
- Semantic operator panel: `operator_hmi.py`.
- Graph/last-session presentation: `operator_dashboard.py`, `telegram_panel.py`.
- Ownership/safety controls: `rd_control_mode.py`, `rd_autonomous_mode.py`,
  `rd_hands_off_release.py`, `rd_ownership_recovery.py`.

### Callback ownership inventory

Точные literal registrations, найденные статическим AST inventory:

| Callback family/literal | Registered owner |
|---|---|
| `ai_analysis`, `charge_back`, `charge_modes`, `custom_cancel`, `dash_back`, `entities_status`, `info_full`, `logs`, `menu_off`, `power_toggle`, `profile_custom`, `profile_*`, `refresh`, `chart_*`, `off_preset_*` | `bot_legacy.py` |
| `operator_done`, `operator_details`, `operator_graph`, `operator_graph_*`, `operator_more`, `operator_pause_toggle`, `operator_refresh`, `operator_service_details`, adopted stop callbacks | `operator_navigation_recovery.py`, `operator_hmi.py` |
| `operator_managed_mix_stop*`, `rd_managed_mix*`, `rd_managed_adopt*` | `rd_managed_mix_adoption.py`, `rd_managed_adoption.py` |
| `rd_autonomous_*` | `rd_autonomous_mode.py` |
| `rd_hands_off_*` | `rd_control_mode.py`, `rd_hands_off_release.py` |
| `rd_live_mix*` | `rd_live_adoption.py` |
| `rd_ownership_*` | `rd_ownership_recovery.py` |
| `v2_batteries`, `v2_battery_add`, `v2_battery_start`, `v2_manual*`, `v2_mix*`, `v2_profile*`, `v2_quick*`, `v2_sg*`, `v2_bat_intent_*`, `v2_mbind:*` | corresponding `v2_bot_ui.py`, `v2_bootstrap.py`, `manual_*`, `v2_mix_mode.py`, `v2_sg_ui.py` |

Тест `tests/test_callback_ownership.py` подтверждает отсутствие дубликатов
точных literal registrations. Prefix/negative-filter handlers и порядок
installer composition остаются отдельным risk surface; это не классифицировано
как неизвестный owner, но требует target registry в будущей фазе.

## 6. Persistence и restore ownership

| Concern | Read | Write | Restore decision | Risk |
|---|---|---|---|---|
| Charge session | `ChargeController.try_restore_session` и legacy callers | `_save_session`, controller V2 override | `bot_legacy` paths + `bot.py` deferred replay | duplicate invocation/order |
| Manual session | `ManualSessionManager._load` | `_persist` | Manual manager; no implicit Output ON after restart | manager/app coupling |
| Diagnostic state | `diagnostic_persistence` load/recover | journal `_persist` | `recover_diagnostic_persistence` from `bot.py` | separate lifecycle |
| Ownership mode | `RdControlModeManager._load` | `_write_mode` | control mode + edge observation | authority split with autonomous |
| Charge DB/history | `database.get_db` queries | DB record functions | no charging authority restore | cached module connection |

Startup ordering currently is:

```text
bot.py main
  -> init_v2_storage
  -> create reconcile_startup_authority task
  -> start physical-test control
  -> bot_legacy.main
       -> legacy background tasks
       -> legacy restore/readback paths
       -> Telegram polling
```

The startup gate wraps ordinary actuator and restore calls; AUTONOMOUS/UNKNOWN
must remain fail-closed. The distributed restore callers are the principal
consolidation target, not a reason to change behavior in Phase 1.

## 7. Safety ownership

| Safety rule | Current owner | File/function | Dependencies | Target owner |
|---|---|---|---|---|
| fail-closed Output ON | V2 safety + HA gate | `runtime_safety_v2.py`, `hass_api.py:turn_on` | fresh telemetry, setpoint/protection/readback | `SafetyEngine` |
| transactional Output coordinator | coordinator | `safe_output.py:SafeOutputCoordinator` | `HAAdapter` | `SafetyEngine.output` |
| verified Output OFF | runtime safety/ownership | `runtime_safety*.py`, `rd_control_mode.py` | readback and edge response | `SafetyEngine` |
| edge lease | runtime/edge contract | `runtime_safety*.py`, guardrails | ESPHome lease entities | `SafetyEngine.lease` |
| AUTONOMOUS authority | coordinator | `rd_autonomous_mode.py` | edge ACK, persistent bit, control mode | `OwnershipEngine` |
| HANDS_OFF boundary | manager | `rd_control_mode.py` | durable mode, verified OFF/release transaction | `OwnershipEngine` |
| startup authority | gate | `rd_startup_authority.py` | edge observation, restore callbacks | `RuntimeApp.startup` |
| watchdog containment | incident task | `soft_watchdog_containment.py`, legacy loops | telemetry/readback, safety stop | `SafetyEngine` |
| thermal/protection rules | controller + safety | `charge_logic.py`, `runtime_safety_v2.py` | telemetry and recipes | `SafetyEngine` + controller policy |

Safety ownership is layered intentionally. Future extraction must preserve the
ordering: safety and ownership veto actuator intent; UI and persistence do not
become safety owners.

## 8. Background task inventory

| Task | Created where | Lifetime supervised | Failure behavior |
|---|---|---|---|
| startup authority reconciliation | `bot.py:main` | cancelled in `bot.py` finally | retries/read-only or containment; fail-closed |
| physical-test server | `bot.py:main` / control object | explicit `start/stop` | isolated bench surface |
| DB cleanup | `bot_legacy.py:main` | task created, legacy loop | periodic retry behavior in loop |
| data logger | `bot_legacy.py:main` | task created, legacy loop | loop-local logging/retry |
| charge monitor | `bot_legacy.py:main` | task created, V2 guard replaces callable | network/error retry |
| soft watchdog | `bot_legacy.py:main` | task created | containment through safety path |
| legacy watchdog | `bot_legacy.py:main` | task created | legacy safety path/scaffold |
| charge notifications | `bot_legacy.py:_charge_notify` | fire-and-forget | safe message fallback/logging |
| dashboard refresh | `bot_legacy.py` handlers | fire-and-forget | UI refresh failure isolated |
| Manual session loop | `manual_mode.py:ManualSessionManager.start` | manager holds task and cancels on stop | stop/containment via manager |

Главный риск — task registry отсутствует как единый lifecycle owner; фактические
owners найдены, но supervision распределён.

## 9. Legacy dependency map

| Legacy module | Used by | Purpose | Replacement candidate | Removal condition |
|---|---|---|---|---|
| `bot_legacy.py` | `bot.py`, all installers and tests | Telegram globals, handlers, loops, restore and action executor | `RuntimeApp` + explicit adapters | all callers moved; no legacy import |
| `charge_logic.py:ChargeController` | `ChargeControllerV2` inheritance and scaffold | established mechanics, safety/session behavior | `ChargeState` + V2 controller | parity tests and physical safety gates |
| legacy Telegram router | all UI installers | shared Dispatcher/Router and handler registry | `TelegramUI` | callback registry migrated |
| legacy session file path | controller/restore callers | continuation compatibility | persistence interface | DB/JSON compatibility verified |
| legacy action executor | `bot_legacy.py` periodic tick | turns controller action dict into HA calls | controller/safety command port | all actuator calls through explicit port |
| `v1_ui_compat.py` | compatibility mode/legacy presentation | old UI fallback | explicit compatibility adapter | V2 UI acceptance and rollback plan |

Название `legacy` не означает автоматически неиспользуемый код: `ChargeController`
и action executor реально участвуют в current V2 composition. Поэтому удаление
или замена допустимы только после доказанной parity и safety regression.

## 10. Critical conflicts and migration blockers

Критические conflicts:

1. `bot.py`/`bot_legacy.py` делят lifecycle и module globals.
2. V2 transition authority использует legacy controller scaffold.
3. Restore имеет несколько callers, хотя startup gate задаёт единую внешнюю
   authority boundary.
4. Actuator methods последовательно monkey-patched несколькими safety/ownership
   installers; порядок композиции является частью поведения.
5. Background task lifetime не централизован.

Migration blockers:

- нет единого explicit dependency container;
- нет единого `ChargeState` write owner;
- нет полного callback registry для prefix/negative-filter semantics;
- нет доказанной полной замены legacy action executor;
- физическая validation остаётся обязательной для edge/lease/safety contract.

Неизвестных владельцев по обследованным responsibility-категориям не найдено;
неопределённость заключается в распределённом ownership и порядке wrappers.

## Phase 1 result

Понятны владельцы lifecycle, dependencies, state, output, callbacks, persistence,
safety, background tasks и legacy boundaries. Phase 1 — PASS как inventory.

Следующий рекомендуемый этап: отдельный design/implementation gate для
`RuntimeApp` skeleton с нулевым изменением actuator semantics. До его начала
нельзя удалять legacy или менять controller ownership.

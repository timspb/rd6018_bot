# V3 Runtime Migration Plan

Статус: Phase 0 — architecture inventory

Дата фиксации: 2026-09-13

## Baseline и границы

Инвентарь зафиксирован от approved baseline:

```text
28d7f83dffa3f0aa9929b5fcc5246f704b830e94
```

Рабочая ветка:

```text
codex/v3-runtime-consolidation
```

Этот документ описывает текущую композицию и целевое распределение ownership.
На Phase 0 код не переносится, `bot_legacy.py` не удаляется, production branch,
node 101 и ESPHome не затрагиваются.

## Current ownership map

### Application и lifecycle

- `bot.py` является тонким V2 entrypoint/shim.
- Он импортирует `bot_legacy` как `_legacy`, последовательно вызывает множество
  `install_*` функций и в конце заменяет `sys.modules[__name__]` на legacy-модуль
  для сохранения общих globals/monkeypatch-семантик.
- `bot.py` владеет V2 `main()`: инициализация storage, startup-authority
  reconciliation, physical-test control и вызов legacy `main()`.
- Telegram `Bot`, `Dispatcher`, `Router`, общие runtime globals и исторические
  handlers фактически находятся в `bot_legacy.py`.

### Telegram и callbacks

- Базовые Telegram handlers и router принадлежат `bot_legacy.py`.
- V2 presentation и дополнительные handlers устанавливаются через
  `v2_bootstrap.py`, `v2_bot_ui.py`, `manual_text_v2.py`, `v2_mix_mode.py`,
  `v2_sg_ui.py` и `telegram_panel.py`.
- Семантический HMI добавляется поздно через `operator_hmi.py`, а navigation,
  managed stop, destructive guard, output truth и ownership recovery добавляются
  отдельными композиционными слоями.
- Проверка точных literal callback registrations существует в
  `tests/test_callback_ownership.py`; динамические/prefix callback boundaries и
  полный жизненный цикл callback пока не имеют единого registry-владельца.

### Controller и transitions

Фактическая цепочка наследования production controller:

```text
ChargeController
  -> ChargeControllerV2
    -> ProductionChargeControllerV2
      -> DiagnosticProductionChargeControllerV2
```

Дополнительные transition/evidence и strategy boundaries подключены через
`auto_strategy_v2.py`, `v2_authority.py`, `first_stage_evidence.py`,
`mix_active_authority.py`, `recovery_policy.py` и shadow/scaffold код.

`ChargeControllerV2` всё ещё вызывает legacy-механику как общий safety/mechanics
scaffold. Поэтому transition authority и lifecycle state сейчас распределены
между V2 decision слоями и наследуемым `ChargeController`.

### State и persistence

- Основной charging state (`current_stage`, active/session markers, timers,
  chemistry и counters) мутируется controller-слоями, с legacy полями внутри
  `ChargeController` и V2 полями в controller subclasses.
- Managed Manual state принадлежит `ProductionManualSessionManager` из
  `manual_runtime_v2.py`, использующему `ManualSessionManager` из `manual_mode.py`
  и `manual_session_v2.json`.
- Legacy charging continuation использует `charge_session.json` через
  `charge_logic.py` и `bot_legacy.py`.
- Diagnostic persistence отделена в `diagnostic_persistence.py`; registry,
  history и charge records хранятся через `database.py`,
  `battery_registry.py` и diagnostic stores.
- Ownership state имеет собственные durable boundaries:
  `RdControlModeManager` (`rd_control_mode_v2.json`) и edge autonomous evidence;
  это не должно сливаться с chemistry/session state.

### Safety, ownership и output

- Базовый runtime safety собран в `runtime_safety.py`,
  `runtime_safety_v2.py` и `safe_output.py`.
- `SafeOutputCoordinator` и `HassClient.safe_enable_output()` являются
  transactional/fail-closed границей разрешения Output ON.
- `hass_api.py` предоставляет HA readback и actuator calls (`turn_on`,
  `turn_off`, setpoints, protection/readback). Вызовы достигаются через legacy
  globals и затем ограничиваются guard/coordinator слоями.
- `production_guardrails_v2.py`, `soft_watchdog_containment.py`,
  `live_output_readback_v2.py` и operator guards добавляют защитные boundaries
  поверх уже созданного приложения.
- `RdControlModeManager` владеет `PB_MANAGED`/`HANDS_OFF`; `rd_autonomous_mode.py`
  добавляет отдельную edge-authoritative AUTONOMOUS ось. AUTONOMOUS не является
  синонимом HANDS_OFF и блокирует bot actuator authority.
- `rd_startup_authority.py` разрешает startup authority по edge state и держит
  обычные actuator/restore paths fail-closed до разрешения. `rd_hands_off_*`,
  adoption и recovery являются отдельными transaction boundaries.

### Composition adapters

Текущие адаптеры `install_*` — временные точки композиции, а не отдельные
ownership-модели. Полный список нужно мигрировать по одному владельцу и с
регрессионным тестом:

| Boundary | Текущая функция | Роль | Phase 0 решение |
|---|---|---|---|
| V2 bootstrap | `v2_bootstrap.install_v2` | controller/session/UI composition | оставить до отдельной миграции |
| safety | `install_v2_runtime_safety` | safety guard | сохранить как safety adapter |
| output truth | `install_output_state_readback`, `install_operator_output_truth` | canonical readback/render guard | сохранить boundary, перенести ownership позже |
| ownership | `install_rd_control_mode`, `install_rd_autonomous_mode` | PB/HANDS_OFF/AUTONOMOUS | сохранить отдельные authorities |
| startup | `install_rd_startup_authority_gate` | pre-restore authority gate | мигрировать последним среди startup paths |
| managed/adoption | `install_*adoption`, `install_rd_hands_off_release` | explicit transactions | не смешивать с AUTONOMOUS |
| UI | `install_operator_hmi`, `install_v2_ui`, `install_panel_last` | presentation/callback composition | свести к единому UI owner |
| tests | `install_physical_test_control*` | opt-in bench-only controls | оставить изолированными и disabled by default |

## Target ownership map

Целевая схема после миграции — один application container и явные порты:

```text
RuntimeApp
├── Lifecycle / startup authority
├── TelegramUI (единственный callback owner)
├── ChargeController (единственный transition owner)
├── ChargeState (единственный владелец mutable chemistry/session state)
├── OwnershipEngine (PB_MANAGED / HANDS_OFF / AUTONOMOUS)
├── SafetyEngine (lease, protection, verified OFF/ON)
├── HAAdapter (readback и transactional calls)
├── RDAdapter (edge identity/authority evidence)
└── Persistence (явные session/ownership/diagnostic stores)
```

Правила target ownership:

1. `RuntimeApp` владеет lifecycle и передаёт зависимости явно; runtime package
   не импортирует `bot_legacy`.
2. `TelegramUI` регистрирует каждый callback один раз; UI не меняет controller
   state напрямую и не вызывает обходные HA actuator paths.
3. `ChargeController` принимает intent и evidence, единолично применяет
   transitions; safety/ownership могут veto, но не создают скрытую вторую FSM.
4. `ChargeState` — единственный владелец mutable stage/timer/session state;
   persistence получает snapshots/commands через этот owner.
5. `OwnershipEngine` остаётся отдельным от chemistry и не превращает
   `HANDS_OFF` в AUTONOMOUS.
6. `SafetyEngine` остаётся выше всех transition решений; Output ON только через
   verified transactional path, Output OFF и uncertainty — fail-closed.
7. `HAAdapter` и `RDAdapter` не содержат Telegram semantics и не владеют
   charging transitions.

## Инварианты миграции

Ни один этап миграции не может нарушить:

- `PB_MANAGED`, `HANDS_OFF` и `AUTONOMOUS` остаются различными authority states;
- AUTONOMOUS edge evidence блокирует bot actuator commands, managed restore и
  lease interference; telemetry/readback остаются доступными;
- startup с неизвестным edge state не принимает молча ни AUTONOMOUS, ни
  PB_MANAGED authority;
- `safe_enable_output()`/`SafeOutputCoordinator` и positive readback сохраняют
  fail-closed семантику;
- lease arm/renew/expiry/trip, verified Output OFF и protection checks не
  заменяются UI или controller shortcuts;
- возврат к Pb authority требует подтверждённого Output OFF и не возобновляет
  старую сессию неявно;
- существующие V2 transition evidence, Manual timers, MINIMUM/DELTA/STOP и
  restore tests остаются зелёными.

## Порядок будущей миграции и stop gates

1. Зафиксировать ownership inventory (этот документ).
2. Выделить `RuntimeApp` только с dependency injection, без изменения authority.
3. Перенести Telegram/callback registration и добавить запрет legacy import.
4. Выделить `ChargeState` и controller transition owner, сохранив safety wrappers.
5. Перенести persistence через explicit interfaces и проверить DB/JSON compatibility.
6. Удалять composition wrappers только после focused и full unittest evidence.
7. Выполнить regression/physical gates для startup, Output, lease, AUTONOMOUS и
   HANDS_OFF до любого production consideration.

Stop gate для каждого шага: любой новый actuator write, изменение ownership
границы, restore behavior, schema compatibility или safety test failure блокирует
следующий шаг и требует отдельного forensic отчёта.

## Phase 0 result

Инвентарь завершён. На этой фазе изменяется только документация. Runtime,
ESPHome/YAML, firmware, main и node 101 не изменялись. RuntimeApp extraction,
удаление legacy ownership и удаление monkey-patch composition отложены на
последующие отдельные, проверяемые этапы.

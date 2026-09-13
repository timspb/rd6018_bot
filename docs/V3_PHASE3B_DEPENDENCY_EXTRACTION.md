# V3 Phase 3B — dependency container

Статус: infrastructure skeleton only

Baseline: `7f7166b5f3ced9e0d22e503de943c3a899e81886`

## Что создано

`RuntimeDependencies` в `runtime/dependencies.py` теперь является явным
пассивным контейнером инфраструктурных ссылок:

- `config` — configuration reference;
- `storage` — storage service/reference;
- `persistence` — persistence access boundary;
- `hass` — HA client reference;
- `logger` — runtime logger;
- `clock` — injectable time source.

`RuntimeApp` принимает этот контейнер и владеет его lifetime вместе с
`LifecycleManager`. По умолчанию container не создаёт production integrations:
все external references остаются `None`, кроме стандартного logger и clock.

## Что намеренно осталось вне container

В Phase 3B не добавлены и не создаются:

- Telegram `Bot`, `Dispatcher`, `Router`;
- `ChargeController`/ChargeEngine;
- `OutputAdapter` и actuator methods;
- SafetyEngine, lease, AUTONOMOUS, HANDS_OFF;
- ESP control или RD command path;
- UI и business state.

Таким образом, текущий `bot.py`/`bot_legacy.py` продолжает работать без изменения
композиции или поведения. Legacy globals, singleton `HassClient`, controller,
database connection и session stores пока остаются в своих текущих владельцах;
они будут подключаться только отдельными migration steps через explicit wiring.

## Dependency inventory

| Object | Current owner | Phase 3B target | Remaining risk |
|---|---|---|---|
| configuration | config/module consumers | `RuntimeDependencies.config` | module globals not migrated |
| storage initialization | `v2_bootstrap`/startup | `RuntimeDependencies.storage` | startup ordering remains legacy |
| DB/persistence access | `database.py` and stores | `RuntimeDependencies.persistence` | cached module connection |
| HA client | `bot_legacy` module global | `RuntimeDependencies.hass` | wrapper order remains current runtime contract |
| logging | module loggers/legacy globals | `RuntimeDependencies.logger` | logger ownership not unified |
| time | direct `time` calls | `RuntimeDependencies.clock` | no consumers migrated yet |

## Tests

`tests/test_runtime_app_skeleton.py` проверяет создание container, передачу в
RuntimeApp, lifecycle, отсутствие `bot_legacy`, отсутствие actuator capability и
отсутствие forbidden controller/UI/lease/ESP slots.

Следующий этап: отдельный gate для `ChargeState` и `ChargeProgram` boundary.
Контроллер, UI и legacy removal до него не переносятся.

Phase 3B не меняет runtime behavior, production, node 101, ESPHome/YAML или
firmware.

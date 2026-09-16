# V3 Phase 3A — RuntimeApp skeleton

Статус: skeleton only

Baseline: `68bc2ebe8a9600098d04fed07b18e7b35b0db967`

## Создано

Добавлен изолированный пакет:

```text
runtime/
├── __init__.py
├── app.py
├── lifecycle.py
└── dependencies.py
```

`RuntimeApp` владеет ссылкой на `RuntimeDependencies` и единственным
`LifecycleManager`. Lifecycle имеет состояния `CREATED`, `STARTING`, `RUNNING`,
`STOPPING`, `STOPPED`, а `start()`/`stop()` являются идемпотентными на уже
достигнутом состоянии.

## Что намеренно не перенесено

Skeleton не импортирует и не создаёт:

- `bot_legacy` или Telegram `Bot`/`Dispatcher`/`Router`;
- `ChargeController` или любой charge engine;
- `HassClient`, `OutputAdapter` или RD command path;
- safety, lease, ownership, AUTONOMOUS или HANDS_OFF components;
- persistence connection и background tasks.

`RuntimeDependencies` содержит только пассивные optional slots для будущего
explicit wiring. Все они по умолчанию `None`; runtime behavior current bot не
изменяется.

## Проверки Phase 3A

Добавлен `tests/test_runtime_app_skeleton.py`, проверяющий создание приложения,
lifecycle start/stop, отсутствие импорта `bot_legacy` и отсутствие actuator
capability.

## Следующий migration step

Следующий шаг — отдельный design/implementation gate для dependency wiring через
совместимые adapters. Он должен сохранять текущие object identity, safety wrapper
order, ownership boundaries и rollback path. Legacy runtime ещё не переносится и
не удаляется.

Phase 3A не меняет production entrypoint, main, node 101, ESPHome/YAML,
firmware или actuator semantics.

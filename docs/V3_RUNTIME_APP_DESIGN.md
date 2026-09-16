# V3 RuntimeApp Design

Статус: Phase 2 — RuntimeApp design gate

Baseline:

```text
fa7eab7bcbb3d47987ca5de38ea411f62bc0ec9a
```

Это архитектурный контракт, а не production implementation. На этой фазе не
создаются классы, не переносится `bot_legacy.py`, не меняются actuator semantics,
safety, ownership, AUTONOMOUS, HANDS_OFF, lease, ESPHome или production.

## 1. Target runtime shape

```text
RuntimeApp
├── LifecycleManager
├── TelegramUI
├── ChargeEngine
├── SafetyEngine
├── OwnershipManager
├── PersistenceStore
├── HAAdapter
└── OutputAdapter
```

`RuntimeApp` — единственный composition root и lifecycle owner. Его задача —
создать зависимости, связать порты и передать управление одному lifecycle
manager. Он не принимает chemistry decisions и не вызывает RD/HA напрямую.

Ownership boundaries:

- `ChargeEngine` вычисляет intent по state, measurements и program.
- `SafetyEngine` разрешает, ограничивает или отклоняет intent.
- `OutputAdapter` — единственный физический actuator port.
- `OwnershipManager` владеет `PB_MANAGED`, `HANDS_OFF`, `AUTONOMOUS`.
- `TelegramUI` является единственным callback/command owner.
- `PersistenceStore` владеет чтением/записью durable state, но не решает,
  можно ли включать Output.

## 2. Runtime lifecycle

### LifecycleManager owns

| Responsibility | Contract | Current migration source |
|---|---|---|
| startup | создать зависимости, init persistence, разрешить startup authority, затем открыть ordinary work | `bot.py:main`, `rd_startup_authority.py`, `bot_legacy.py:main` |
| shutdown | отменить задачи, остановить UI/transport, закрыть persistence и adapters | `bot_legacy.py:on_shutdown`, `bot.py` `finally` |
| background tasks | зарегистрировать каждую задачу, хранить handle, отменять и наблюдать её | `bot_legacy.py:main` и handler `create_task` calls |
| reconnect | delegated read-only reconnect/retry policy for HA/Telegram; no implicit actuator intent | `hass_api.py`, Telegram startup resilience |
| graceful stop | orderly stop of tasks and adapters; physical stop remains SafetyEngine transaction | current shutdown/containment paths |

Правило: один `RuntimeApp` имеет один `LifecycleManager`, один startup sequence
и один task registry. Ни один adapter, UI module или controller не запускает
свой независимый application main loop.

Startup order:

```text
create dependencies
  → load durable ownership/state
  → observe edge authority
  → resolve startup authority
  → start supervised read-only/background tasks
  → start Telegram transport
```

До разрешения authority все обычные actuator и restore paths закрыты fail-closed.
При `UNKNOWN` нельзя молча выбрать ни `PB_MANAGED`, ни `AUTONOMOUS`.

## 3. Dependency injection

`RuntimeApp` создаёт и сохраняет ровно один экземпляр каждого runtime service.
Конкретные реализации могут оставаться текущими adapters на переходных фазах.

| Dependency | Owner | Lifetime | Created where | Consumers |
|---|---|---|---|---|
| `HAAdapter` | `RuntimeApp` | process lifetime | composition root | SafetyEngine, OutputAdapter, telemetry readers |
| `OutputAdapter` | `RuntimeApp` / SafetyEngine boundary | process lifetime | composition root | SafetyEngine only for physical writes |
| `PersistenceStore` | `RuntimeApp` | process lifetime | startup before restore | ChargeState, ownership, manual/diagnostic stores |
| `ChargeState` | `RuntimeApp` | process lifetime | composition root | ChargeEngine, UI read models, PersistenceStore |
| `ChargeEngine` | `RuntimeApp` | process lifetime | composition root | Lifecycle tick, UI intents |
| `SafetyEngine` | `RuntimeApp` | process lifetime | composition root | lifecycle, ownership and controller intent gates |
| `OwnershipManager` | `RuntimeApp` | process lifetime | composition root | startup, UI, SafetyEngine |
| `TelegramUI` | `RuntimeApp` | process lifetime | after authority gate | Telegram transport, render models |
| `TaskRegistry` | `LifecycleManager` | process lifetime | lifecycle startup | all supervised loops |

`Bot`, `Dispatcher`, `Router`, `HassClient`, controller and stores не должны
оставаться скрытыми module singletons в target design. Compatibility adapters
могут временно ссылаться на них, но только через явные constructor dependencies
и с отдельным removal condition.

## 4. State ownership

Единый mutable source of truth:

```text
ChargeState
```

`ChargeState` владеет:

- mode и program identity;
- stage;
- target voltage/current и protection targets;
- stage/finish/hold timers;
- completion and stop reason;
- active session metadata;
- state needed to render current progress.

`OwnershipManager` владеет ownership state отдельно:

- `PB_MANAGED`;
- `HANDS_OFF`;
- edge-authoritative `AUTONOMOUS`;
- startup authority resolution and transition evidence.

Запрещено target design:

```text
legacy mutable stage/state  +  parallel V2 mutable stage/state
```

Программы и UI читают state через read model/immutable snapshot и не мутируют
его напрямую. `PersistenceStore` принимает state snapshots и возвращает
validated restore candidates; решение о restore принимает LifecycleManager совместно
с OwnershipManager и SafetyEngine.

## 5. Controller boundary

```text
ChargeEngine
  receives:
    Measurements
    ChargeProgram
    ChargeState snapshot
  produces:
    ChargeIntent
```

`ChargeEngine` не импортирует и не знает о Telegram, HA, ESP, Output adapter,
lease implementation или transport. Его результат — описание намерения:

```text
ChargeIntent = desired stage/setpoints, requested transition, reason, evidence
```

Это не physical command. Применение intent возможно только через SafetyEngine.

## 6. ChargeProgram boundary

```text
ChargeProgram.evaluate(
    state,
    measurements,
) -> ChargeIntent
```

Первичные program policies:

- `Minimum` — критерий минимального тока/подтверждения согласно действующей
  стратегии;
- `Delta` — criterion/confirmation/hold согласно действующему контракту;
- `Manual` — operator-defined values and timers, без обхода safety/ownership.

Program policy отвечает только за decision evidence и intent. Она не имеет права:

- вызывать `turn_on` или `turn_off`;
- писать в HA или ESP;
- arm/disarm/renew lease;
- менять ownership state;
- выполнять Telegram/UI actions.

## 7. Safety boundary

```text
ChargeIntent
    ↓
SafetyEngine
    ↓
OutputAdapter
    ↓
RD / HA edge
```

`SafetyEngine` owns:

- fail-closed decision for Output ON;
- fresh telemetry and setpoint/protection readback requirements;
- transactional Output ON/OFF and positive confirmation;
- lease/protection/thermal/communication containment;
- safe behavior on uncertainty and startup quarantine.

`OutputAdapter` owns transport details and canonical readback plumbing, но не
решает, разрешён ли intent. `ChargeEngine`, `ChargeProgram`, TelegramUI и
PersistenceStore не могут напрямую вызвать actuator methods.

Existing invariants remain unchanged: AUTONOMOUS blocks bot actuator authority,
HANDS_OFF is distinct, verified Output OFF is required where specified, and
unknown edge authority remains fail-closed.

## 8. UI boundary

```text
TelegramUI
├── commands
├── callbacks
├── rendering
└── keyboards
```

`TelegramUI` владеет registration and dispatch of commands/callbacks, rendering
and keyboard construction. Один callback literal/prefix semantic boundary имеет
одного owner-а. UI передаёт typed user intent в `ChargeEngine`,
`OwnershipManager` или read-only query service; UI не вызывает HA напрямую и не
меняет `ChargeState`.

`operator_hmi.py`, `v2_bot_ui.py`, `manual_*`, `telegram_panel.py` и legacy UI
на migration period являются source modules. Их semantics должны быть
перенесены через tests, без изменения user-visible contract без отдельного
решения.

## 9. Persistence and restore boundary

`PersistenceStore` предоставляет отдельные namespaces/interfaces для:

- `ChargeState` continuation;
- Manual session;
- diagnostic journal;
- ownership mode/evidence;
- DB history/records.

Restore protocol:

```text
PersistenceStore.read candidates
    → LifecycleManager obtains fresh measurements
    → OwnershipManager resolves authority
    → SafetyEngine validates any physical realization
    → ChargeState accepts one validated restore
```

Ни один saved session не может автоматически вернуть управление при
`AUTONOMOUS`, `HANDS_OFF` или `UNKNOWN`; отсутствие/повреждение state остаётся
fail-closed и не создаёт AUTONOMOUS authority.

## 10. Migration order

| Step | Scope | Risk | Rollback point | Required tests |
|---|---|---|---|---|
| 1. Runtime container | создать passive `RuntimeApp` composition boundary | import/lifecycle regression | current `bot.py` entrypoint | compile, startup, polling |
| 2. Dependency wiring | передать adapters/stores explicitly | singleton identity/monkeypatch drift | compatibility factory | focused DI, HA/readback, safety |
| 3. State extraction | ввести один `ChargeState` snapshot/write path | stage/timer/restore drift | legacy state adapter | minimum, delta, manual, stop, restore |
| 4. Controller boundary | перевести decisions в `ChargeEngine`/program interfaces | transition or recipe regression | V2 controller adapter | full charge matrix, transition evidence |
| 5. UI migration | перенести commands/callbacks/rendering | callback shadow/user flow regression | V1/V2 UI compatibility switch | callback ownership, `/start`, manual, dashboards |
| 6. Legacy removal | удалить adapters только после proof of non-use | hidden production dependency | last adapter-backed release | full unittest + deployment/bench gates |

Каждый шаг — отдельный commit и rollback point. Любой новый actuator write,
изменение ownership, restore, lease или safety result блокирует следующий шаг.

## 11. Design gate result

После реализации этого дизайна однозначно определены:

- единственный runtime/lifecycle owner: `RuntimeApp`;
- единственный mutable charge-state owner: `ChargeState`;
- единственная physical write boundary: `OutputAdapter` под контролем
  `SafetyEngine`;
- единственный callback/UI owner: `TelegramUI`;
- граница программ: `ChargeProgram → ChargeEngine → ChargeIntent`;
- граница safety: `ChargeIntent → SafetyEngine → OutputAdapter → RD`.

Known risks: текущий `bot.py`/`bot_legacy.py` module alias, distributed restore,
legacy controller scaffold, ordered method wrappers и unsupervised background
tasks остаются в коде до последующих фаз. Это design constraints, а не внесённые
изменения.

Phase 2 PASS: design готов к отдельному review gate. Runtime, main, production,
node 101, ESPHome/YAML и firmware не изменялись.

# RD6018 Bot V3 Project Runbook

## 1. Назначение проекта

Проект — не просто контроллер RD6018. Он разделяет операторский интерфейс,
домен зарядки, доказательную телеметрию, диагностику, безопасность и физическое
исполнение:

```text
человек
  |
  v
bot/UI adapter
  |
  v
V3 Runtime
  +-- telemetry evidence
  +-- diagnostics and bank-fault evidence
  +-- charge strategy
  +-- safety and execution policy
  +-- journal/UI model/replay
  |
  v
physical hardware
```

## 2. Главный принцип

Бот — адаптер к оператору («кожаному мешку»). Он принимает намерения, показывает
состояние и передаёт запросы. Бот не владеет зарядом, RD6018 или деталями
оборудования. Любое физическое действие проходит через domain decision, safety,
execution policy, manual gate/lease и readback.

## 3. Текущая архитектура V3

Основные слои:

- Config Layer — параметры и секреты вне кода;
- Telemetry Evidence — snapshots, качество полей, история и аккумулятор Ah;
- Diagnostics — состояние АКБ, bank-fault evidence и diagnostic authority;
- Charge Domain — BatteryProfile, recipe, MAIN/RECOVERY/MIX strategy и intents;
- Safety Evidence/Engine — агрегирует доказательства и fail-closed решения;
- Execution Policy — проверяет prerequisites перед передачей intent;
- Output/Physical Layer — SafeOutputIntent, gate, lease, bridge и readback;
- Journal/UI Model — события и read-only представление;
- Replay/Trace — воспроизводимость решений без железа.

## 4. Charge domain

Единый владелец решений — runtime charge strategy, не bot. Основной путь:

```text
MAIN -> plateau/recovery -> MAIN или MIX -> hold -> SAFE_WAIT/DONE
```

В MIX разделены физические варианты:

- CC: Vmax подтверждается, затем наблюдается подтверждённое падение напряжения
  по ΔV;
- CV: Imin подтверждается, затем наблюдается подтверждённый рост тока по ΔI;
- подтверждённый delta запускает sticky hold;
- current containment в CV MIX стартует через 30 минут и пересчитывается каждые
  10 минут только вниз;
- аномалия внешней температуры или bank fault передаются как safety evidence и
  могут заблокировать заряд.

Числа, времена, лимиты и запасы задаются конфигурацией/recipe, а не
монолитной логикой.

## 5. Battery diagnostics

Решение о продолжении HV-заряда опирается на telemetry quality, battery
diagnostics, bank-fault evidence, temperature integrity и safety evidence.
Если доказан отказ банки с достаточной уверенностью, результатом является
запрет/остановка через SafetyEngine; диагностика сама не пишет в RD.

## 6. Physical architecture

Два независимых коннектора к одному RD6018:

```text
V3 PhysicalBridge Contract
          |
    +-----+------+
    v            v
HAESPConnector  ESPDirectConnector
    |            |
    v            v
  HA 102       ESP 128
      \        /
        RD6018
```

HA и ESP-direct — альтернативные независимые пути, не последовательные звенья
и не автоматический fallback. Текущая конфигурация и порядок доступа описаны в
`config/physical/connectors.yaml`, `ha102.yaml`, `esp128.yaml` и
`docs/V3_BENCH_VALIDATION_PROTOCOL.md`.

## 7. Что сделано

| Commit | Результат |
| --- | --- |
| `02d515c` | config layer |
| `9d23dd0` | read-only HA102/ESP128 transports |
| `27b10fb` | live snapshot evidence |
| `01fae8f` | verified `DISABLE_OUTPUT` path |
| `2a6eb7c` | manual bench lease |
| `b0d9fb4` | pre/post physical verification |
| `37a3220` | independent HA-ESP and ESP-direct connectors |
| `a57fba2` | physical command target verification |
| `25e311c` | first controlled physical execution path |
| `13def3e` | verified-off transition evidence clarification |
| `d4c8e96` | controlled `OFF -> ON -> OFF` bench flow, battery-aware parameters |
| `caa6811` | wait for post-OFF zero-current confirmation |
| `022e01f` | runbook/checklist timing and battery-selection rules |
| `8682eae` | compact charge-panel header with right-aligned MAIN/MIX stage |

Текущий HEAD: `8682eaebe38a00c74b656556dd7c084a4a51de90`.

## 8. Physical execution status

Готово:

- config, capability discovery и два транспорта;
- snapshots/readback и manual gate/lease;
- battery-aware bench selection;
- короткий физический HA-ESP-RD переход с независимым ESP readback:
  `ON` подтверждён за `1.526 с`, `OFF` за `2.546 с`, нулевой ток — отдельным
  readback примерно через `5 с`;
- evidence и ожидание задержанного readback в executor.

Не сделано:

- полноценный заряд через V3;
- production wiring и автоматическое управление;
- независимый полный `OFF -> ON -> OFF` run через ESP-direct;
- замена V2/V1 UI. V1 UI сохраняется отдельно и является источником
  информационных требований.

При физическом тесте всегда: сначала battery voltage, затем Vset из config,
затем V/I/OVP/OCP readback, manual ARM, короткий ON hold, OFF и ожидание
`Output OFF + current 0 A`.

Операторский STOP ручной сессии выполняется через managed-stop workflow с
verified Output OFF. Устаревший callback `power_toggle` после установки этого
workflow не выполняет общий toggle и предлагает обновить панель.

## 9. Configuration model

```text
config/
  physical/   # transports, connectors, bench profile
  charge/     # recipes and limits
  safety/     # safety ceilings
  runtime/    # tolerances, polling and execution timing
  secrets     # only environment/secret references, never values in git
```

Все изменяемые параметры находятся в config и сопровождаются RU/EN
комментариями. Секреты читаются через environment references.

## 10. Journal/UI

UI — read-only consumer ViewModel. Первая строка активной панели имеет вид
`RD6018 · ЗАРЯД · <регулятор>` слева и `MAIN`/`MIX`/`FLOAT` справа; АКБ
показывается отдельной строкой. Он показывает stage/phase, параметры,
таймеры, transition evidence, diagnostics, safety, output и хвост журнала.
Журнал имеет однострочные пользовательские записи и отдельные event records;
форматирование не находится в charge engine. V1 UI не удалять и не менять без
отдельной задачи.

## 11. Operator Application Interface

Текущий PR добавляет изолированный application/presentation/telegram контракт:

```text
Telegram adapter -> OperatorInterface -> OperatorSnapshot -> declarative renderer
```

`OperatorSnapshot` и `PanelLayout` содержат только данные и декларативные действия.
Они не содержат HA/RD/controller объектов. Старый V1/V2 UI и его callbacks пока
остаются production-путём; их прямые связи перечислены в UI-аудите и устраняются
только после parity-проверок.

`application/operator_snapshot_provider.py` — read-only adapter текущего V1/V2
runtime. Он читает live state, `OperatorHmiState`, diagnostics и journal, но не
вызывает start/stop или actuator methods. `application/operator_snapshot_shadow.py`
сравнивает legacy HMI с V3 snapshot.

## 12. Следующие шаги

1. Завершить независимую physical evidence-проверку ESP-direct.
2. Устранить/задокументировать HA control/readback latency без обхода safety.
3. Подключать runtime state к bot adapter через UserCommand/UI boundaries.
4. Закрыть V3 UI parity с V1 без переноса V1 implementation.
5. Только после parity и bench gates — controlled charge bench.
6. Production migration — отдельное решение после физического evidence.

## 13. Запрещённые направления

- bot direct hardware control;
- параллельные несогласованные FSM;
- обход SafetyEngine, ExecutionPolicy, lease или verified readback;
- hardcoded voltage/current/time/limits;
- synthetic authorization или автоматический fallback между коннекторами;
- изменение ESPHome/firmware/node 101 без отдельного разрешения.


## 14. 2026-10-04 — Modular V3 and legacy eradication

Repository authority at the start of this migration:

- canonical remote branch: `main`;
- baseline: `6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`;
- deployed VM104 remains on `c1298ea2df67bba1e4888de6e830b002b5db2fce`;
- deployment/restart/hardware mutation is outside this migration unless separately approved.

### 14.1 Decision

The transitional model where V3 wraps V1/V2 is no longer an acceptable target.
The migration must end with a genuinely modular production V3. Historical code
can be a bounded oracle during parity work, but a migrated capability must not
delegate its ownership back into the monolith.

Authoritative contracts:

- `docs/V3_MODULAR_ARCHITECTURE.md`;
- `docs/V3_UI_MODULAR_ARCHITECTURE.md`;
- `docs/V3_LEGACY_ERADICATION_LEDGER.md`.

### 14.2 Mandatory module boundaries

Production V3 is decomposed into:

1. composition/lifecycle;
2. application intents/use cases;
3. charge programs/stages;
4. signal/evidence;
5. safety concerns;
6. execution transaction;
7. telemetry;
8. ownership/session;
9. persistence;
10. infrastructure adapters;
11. UI/presentation/Telegram transport.

No module may recover a removed dependency by monkey-patching the historical
runtime.

### 14.3 Configuration rule

Every configurable number, duration, threshold, enum or policy value has one
semantic owner and one declaration location in that owner's `variables.py` or
`config.py`.

Every declaration documents:

- key and type;
- unit;
- description;
- owner;
- default;
- range/allowed values;
- provenance;
- override policy;
- change effect (runtime/restart/deploy).

Consumers receive typed configuration. Copying the literal into another module
is prohibited.

### 14.4 UI is a first-class migration workstream

UI parity is not left until the end. Screens, buttons, navigation, components,
graphs and future operator actions are modular.

A new V3 button is a `ButtonSpec` with a stable `UIAction`; it does not contain
a hardware callback. Telegram callback data is a transport concern, not the
application API.

A future screen/button must not require editing `runtime/v2_runtime.py`,
`charge_logic.py`, controller classes, safety or execution modules.

### 14.5 Legacy eradication sequence

#### ERADICATION-01 — prevent legacy resurrection

- retire environment-controlled legacy decision authority;
- hard-deny START when the production START route is absent;
- remove the hidden direct V/I/OVP/OCP/Output START fallback;
- disable direct `bot_legacy.py` execution;
- add architecture/static regression contracts;
- establish module variable metadata and declarative UI primitives.

Gate: no software behavior or hardware values change in the canonical
production route; tests prove removed fallback cannot return.

#### ERADICATION-02 — extract MAIN

- characterize accepted MAIN semantics;
- extract MAIN state/clock/tail/recovery decisions into modular charge code;
- reuse explicit safety/evidence services, not `super().tick()`;
- remove MAIN blanking/time masking of the historical FSM.

Gate: golden traces, restart and failure paths match accepted behavior and the
production MAIN path has no historical FSM transition call.

#### ERADICATION-02a — MAIN decision/config extraction (implemented, pending CI)

- canonical MAIN decision owner: `runtime/charge/strategy/main_authority.py`;
- canonical MAIN variables: `runtime/charge/strategy/main_variables.py`;
- canonical base target selection: `runtime/charge/strategy/main_targets.py`;
- canonical stage-current ceiling declaration: `runtime/safety/variables.py`;
- compatibility `v2_authority.py` re-exports the new MAIN owner;
- transitional production controllers consume these modular owners;
- accepted 72h / 2h / 3h / 3/4 recovery budgets / AGM 14.4→15.0V semantics are regression-tested.
- first-stage tail/plateau/thermal/sag evidence moved to `runtime/charge/evidence/first_stage.py`;
- evidence thresholds live in `runtime/charge/evidence/first_stage_variables.py` with metadata;
- root `first_stage_evidence.py` reduced to a compatibility re-export.

ERADICATION-02 MAIN cutover is now implemented locally: authoritative MAIN uses
`runtime/charge/runtime/main_scaffold.py` for accepted common runtime mechanics
and does not enter historical `ChargeController.tick()`. The MAIN blanking mask
and stage-clock falsification are removed. CI remains the gate before declaring
this boundary merged.

#### ERADICATION-03 — recovery lifecycle

- DESULFATION;
- recovery SAFE_WAIT;
- verified return to MAIN;
- continuation persistence and restart.

Gate: the complete `MAIN -> DESULFATION -> SAFE_WAIT -> MAIN` path is modular
and the old transition path is unreachable.

#### ERADICATION-04 — MIX and final Storage

- CV Imin/Delta-I;
- CC Vmax/Delta-V;
- confirmation spacing;
- sticky active-time hold;
- MIX limit;
- final SAFE_WAIT;
- verified Storage/DONE commit.

Gate: one evidence owner and one FSM path; no legacy Mix timer/Delta branch.

#### ERADICATION-05 — Manual/Custom

Manual is a separate program family sharing safety/execution only. It is not a
special-case escape hatch inside AUTO.

#### ERADICATION-06 — safety and execution convergence

Move all remaining setters/output calls behind the single execution owner.
Safety is split into concern modules and emits typed decisions.

Gate: static production scan finds no direct physical writes outside the
approved physical implementation.

#### ERADICATION-07 — UI cutover

Migrate screens one at a time to canonical ViewModels, `ScreenSpec`,
`ButtonSpec`, `UIAction` and application intents. Remove each old callback
after parity.

Gate: canonical UI imports no historical runtime/controller/HA/ESP modules.

#### ERADICATION-08 — runtime/composition cutover

Replace `_legacy`, `sys.modules` aliasing and top-level installer mutation
with one explicit composition object and lifecycle.

#### ERADICATION-09 — remove historical production graph

When all prior gates pass:

- no `runtime.v2_runtime` production import;
- no historical FSM production import;
- no `bot_legacy` production execution;
- remove remaining compatibility files only after archive/reference capture.

### 14.6 Per-boundary workflow

Every migration increment follows:

```text
characterize
-> modular implementation
-> parity tests
-> restart/failure tests
-> switch one route
-> prove new owner
-> remove old route
-> static no-regression guard
-> exact-head CI
```

Do not keep a fallback mutating path after a successful cutover.

### 14.7 Stop conditions

Stop before mutation/cutover if:

- ownership is ambiguous;
- a safety semantic would change without explicit decision;
- a configuration value has conflicting provenance;
- a second execution owner appears;
- UI needs direct hardware/controller access;
- restart could authorize Output ON from persisted state alone;
- parity evidence is missing.

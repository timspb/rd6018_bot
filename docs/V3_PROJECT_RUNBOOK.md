# RD6018 Bot V3 Project Runbook

## ОБЯЗАТЕЛЬНО: актуальные физические данные — напрямую с ESP Native API

**БРАТЬ АКТУАЛЬНЫЕ ДАННЫЕ С ESP, А НЕ ИЗ HA, СТАРОГО ОТЧЁТА ИЛИ КЭША.**
На node104 авторитетный физический источник — непосредственно ESPHome Native API
контроллера ESP (текущий адрес стенда `192.168.1.28:6053`), через уже
существующий `esp_direct` / `aioesphomeapi` клиент и свежую подписку на
`SensorState` / `BinarySensorState`. Это первый шаг **каждой** проверки
Output, START, STOP, lease, аварии, деплоя и физической приёмки.
Доступность TCP-порта сама по себе **не является** физическим readback.

Каждый раз заново читать с ESP: физический Output **R18**, измеренные U/I,
напряжение АКБ, уставки Vset/Iset, OVP/OCP и защиту R16, lease
armed/generation/remaining/Modbus age, trip/quarantine/autonomous. Проверять
идентичность ESP, типы полей, источник `esp_native_api`, временные метки
подписки и фактическую свежесть; для post-STOP доказательства применять
имеющийся строгий post-command критерий свежего R18 и нулевых U/I.

HA102 — **вторичный путь к тому же ESP**, полезный для независимой сверки,
но не заменяющий прямые ESP Native callbacks. Старые снимки, журналы,
показания Telegram UI и HA-кэш описывают только историю. Не заявлять
`Output OFF` или `PHYSICAL PASS` по ним.

При отсутствии доступа к Native API сначала найти **уже установленный**
ESP direct-клиент и штатный read-only collector, разобраться с доступом.
Если чтение действительно невозможно, написать **ESP ACCESS BLOCKED**,
а не «физическое состояние неизвестно, потому что HA не свежий». Не
симулировать значения, не обходить запреты инструментов и не отправлять
непосредственные ESP-кнопки/Modbus-команды вне единственного ExecutionPort.

Канон и порядок: `docs/ESP_NATIVE_LIVE_EVIDENCE.md`.


## D084 recovery quarantine — 2026-10-17

An ambiguous false result in link-session restoration now enters a sticky,
process-lifetime `SessionRecoveryGuard`. It blocks another automatic restore and
the controller tick for that cycle and later cycles, while the canonical
`ExecutionPort` also denies automatic ON and non-OFF programming paths. The
managed session remains intact; normal live reads, lease renewal, safety
observations, and verified OFF remain available. Existing OVP/OCP, internal
temperature, and operator-configured OFF handling runs before the quarantine.

This is not durable across process restart and has no operator UI clearance
workflow yet. No poll or peer reconnect clears it. An explicit guard rearm API
requires confirmed Output OFF, but production does not currently expose a
caller. Persistent recovery authority and an operator workflow remain a
follow-up design. See `docs/assistant/D084_RECOVERY_QUARANTINE_2026-10-17.md`.
Software tests are not physical validation; edge/PSU bench acceptance remains
outstanding. No hardware, deployment, or credential was used for D084.

## D087 operator recovery clearance — 2026-10-17

The D086 coordinator is now connected to production through the existing
ExecutionPort, controller-owned session persistence, durable quarantine
journal, and a private Telegram two-step route (only when `V2_UI` is enabled).
Clearance requires a nonempty explicit `ALLOWED_CHAT_IDS` allowlist and a
private chat whose sender and chat IDs match; `ALLOW_ALL_CHATS` grants nothing.
The exact incident/session/battery identity is checked before verified OFF.
The post-OFF receipt requires a fresh native register-18 Output=OFF report.
The controller persists a terminal retired-session marker before the journal
tombstone, and the RAM guard releases last. Retired sessions cannot restore and
never auto-start a new charge. See
`docs/assistant/D087_OPERATOR_RECOVERY_CLEARANCE_IMPLEMENTATION_2026-10-17.md`.

## D089 native post-OFF receipt hardening — 2026-10-17

D087 clearance proof now requires a post-completion native ESPHome `SensorState`
callback from the already-selected physical backend. HA REST/live snapshots and
pre-command cached reports cannot certify OFF. The subscription timestamp must
be monotonic and strictly later than the existing verified-OFF transaction,
with numeric zero and callback age no greater than eight seconds; polling is
bounded to ten seconds. Missing native reporting fails closed and leaves
quarantine/session state intact. The boolean OFF API, emergency OFF path, and
actuator write count are unchanged. See
`docs/assistant/D089_NATIVE_POST_OFF_RECEIPT_2026-10-17.md`. This is offline
software evidence only; node104 deployment and physical acceptance were not
performed.

This is software implementation evidence only. No hardware, HA/ESPHome, PSU,
Output ON, or deployment was used. The exact node/firmware and native
register-18 contract remain subject to physical bench acceptance.

## Post-eradication sprint audit — baseline `1f8d9c45c9b543dde7a57f78b6385d01012e7b4f`

The `V2_UI` environment variable remains an intentional presentation-only
disable switch. It does not gate charge authority, safety, ownership, telemetry,
or transactional execution; those installers remain composed when the flag is
disabled. Removing it would remove the documented non-actuating UI rollback
semantics.

The obsolete production quick-start fallback that delegated to `_start_profile`
when the canonical start route was absent was removed. Canonical composition
now fails closed at the callback boundary, and the external `v2_*` callback
tokens remain unchanged as protocol identifiers. Internal production-bootstrap
names were normalized to `_managed_charge_monitor_guard_installed` and
`_battery_start_route`; no persistence, HA, or ESPHome identifiers changed.

This is software evidence only. No node, Telegram, HA, ESPHome, lease, output,
or charger action was performed.

## Current production host authority

The only current production host is node 104. Node 101 is retired and excluded
from all live checks, deployment, and physical validation. References to node
101 later in this runbook are retained only inside historical evidence or
migration records and do not identify the current production target.

## MAIN charge programmed protection registers

Normal managed charging owns Vset/Iset and verifies fresh programmed V/I,
measured electrical and temperature evidence, independent hardware trip status,
the existing edge lease, and transactional Output state. It does not routinely
program OVP/OCP or require their numeric register readbacks. Missing/stale OVP
or OCP readback alone is not a physical trip and must not fault MAIN, its 30
minute Iset ratchet, MAIN resume reconciliation, or ordinary automatic stage
transitions. The Guard still ratchets Iset only downward, requires fresh Iset
acknowledgement and durable journal commit, and retains the existing lease and
ownership checks. Chemistry/absolute voltage and current limits, measured
envelope checks, and native protection-trip detection remain active.

Explicit transactions that request OVP/OCP (including Manual paths) retain
their existing programming and readback checks. Normal automatic charge stages
leave the physical protection registers untouched; this change neither clears
hardware protections nor claims their current physical settings. The optional
OVP/OCP values in `OutputRequest` are transaction-scoped requests, not a global
disable switch. Code/test evidence is not physical acceptance.

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
форматирование не находится в charge engine. Production UI постепенно
нормализуется на declarative screen/button/action contracts; удалённые V1/V2
compatibility-фасады не являются допустимым fallback.

## 11. Operator Application Interface

Текущий production read path:

```text
Telegram adapter -> OperatorInterface -> OperatorSnapshot -> declarative renderer
```

`OperatorSnapshot` и `PanelLayout` содержат только данные и декларативные действия.
Они не содержат HA/RD/controller объектов. `application/operator_snapshot_provider.py`
читает explicit `OperatorReadSource`, diagnostics и journal, но не вызывает
start/stop или actuator methods. Старый shadow comparator и V1 UI compatibility
wrapper удалены после отсутствия production callers.

## 12. Следующие шаги

1. Продолжить удаление test/shadow-only migration islands, не достижимых от `bot.py`.
2. Переименовать или поглотить production-reachable `v2_*` модули только после
   миграции их callers и parity/full-suite доказательства.
3. Свести UI/runtime composition к нейтральным модульным именам без compatibility facades.
4. На каждом boundary обновлять `docs/README.md`, runbook и eradication ledger.
5. Production node 104 и физический заряд остаются отдельным operational boundary.

## 13. Запрещённые направления

- bot direct hardware control;
- параллельные несогласованные FSM;
- обход SafetyEngine, ExecutionPolicy, lease или verified readback;
- hardcoded voltage/current/time/limits;
- synthetic authorization или автоматический fallback между коннекторами;
- изменение ESPHome/firmware/node 104 без отдельного разрешения.


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

#### ERADICATION-02a — MAIN decision/config extraction (implemented; exact-head CI PASS)

- canonical MAIN decision owner: `runtime/charge/strategy/main_authority.py`;
- canonical MAIN variables: `runtime/charge/strategy/main_variables.py`;
- canonical base target selection: `runtime/charge/strategy/main_targets.py`;
- canonical stage-current ceiling declaration: `runtime/safety/variables.py`;
- compatibility `charge_authority.py` re-exports the new MAIN owner;
- transitional production controllers consume these modular owners;
- accepted 72h / 2h / 3h / 3/4 recovery budgets / AGM 14.4→15.0V semantics are regression-tested.
- first-stage tail/plateau/thermal/sag evidence moved to `runtime/charge/evidence/first_stage.py`;
- evidence thresholds live in `runtime/charge/evidence/first_stage_variables.py` with metadata;
- root `first_stage_evidence.py` reduced to a compatibility re-export.

ERADICATION-02 MAIN cutover is implemented: authoritative MAIN uses
`runtime/charge/runtime/main_scaffold.py` for accepted common runtime mechanics
and does not enter historical `ChargeController.tick()`. The MAIN blanking mask
and stage-clock falsification are removed. Handoff exact-head CI run `#1510`
(`37141127400`) passed on Python 3.10, 3.11 and 3.12 at
`396b364b79816366380ee89d452256d1e0bacf08`.

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

### 14.8 Current checkpoint — 2026-10-04

Repository/worktree authority for handoff:

- canonical remote base remains `main@6eb6980d1e4a4aeeb804ae25a59af8e292a3d324`;
- active migration branch: `refactor/v3-modular-legacy-eradication`;
- local migration HEAD before this runbook update: `5bf7bf0a75ed99addc6868952db04512c82b8441`;
- the previously pending local commits through `978f5013eaec1472e0649690854dea4ba45d870d` were successfully pushed to `origin/refactor/v3-modular-legacy-eradication`;
- local worktree is `E:\CODEX\rd6018_v3_modular` and is intentionally isolated from the user's dirty primary worktree `E:\CODEX\rd6018_bot`;
- production VM104 was not deployed/restarted/mutated by this migration. Last confirmed deployed production SHA remains `c1298ea2df67bba1e4888de6e830b002b5db2fce`.

#### Completed locally after remote `2b21f245`

`3f53139649b2cb5a26a5dc4ab26c947fc358f74e` — Move first-stage evidence into modular charge domain

- canonical first-stage evidence moved to `runtime/charge/evidence/first_stage.py`;
- evidence thresholds moved to `runtime/charge/evidence/first_stage_variables.py`;
- root `first_stage_evidence.py` reduced to compatibility import surface;
- production consumers were moved to the canonical evidence module.

`5bf7bf0a75ed99addc6868952db04512c82b8441` — Cut authoritative MAIN off historical tick

- authoritative MAIN no longer enters historical `ChargeController.tick()`;
- MAIN blanking/time masking is removed;
- accepted shared mechanics required by MAIN moved to `runtime/charge/runtime/main_scaffold.py`;
- runtime/safety-owned timing and thresholds are declared in module-local variable files;
- modular MAIN decision/config/target/evidence ownership remains the authority;
- historical superclass still exists for non-migrated stages and compatibility, so this is not whole-controller retirement.

#### Validation at this checkpoint

- `git diff --check`: PASS;
- `python -m compileall -q .`: PASS;
- focused suites PASS:
  - `test_v3_modular_architecture_contract.py`;
  - `test_v3_main_authority_migration.py`;
  - `test_charge_authority.py`;
  - `test_auto_strategy.py`;
  - `test_v2_production_controller.py`;
  - `test_charge_controller.py`;
  - `test_first_stage_evidence.py`;
  - `test_legacy_enable_inventory.py`;
  - `test_start_route_isolation.py`.
- expected synthetic failure-path log traces appeared inside tests, but the suites passed.
- full local suite after `5bf7bf0` has NOT yet been rerun in this checkpoint;
- GitHub CI was triggered after the branch synchronized; exact-head CI must be green before merge/closure.

#### Current plan state

ERADICATION-01 is implemented locally and still needs exact-head CI/remote integration before being marked closed.

ERADICATION-02 MAIN is functionally cut over locally: decision authority, variables, first-stage evidence, base target selection and common MAIN runtime scaffold are modular, and authoritative MAIN no longer calls the historical FSM tick.

Next execution boundary is ERADICATION-03:

1. migrate DESULFATION lifecycle to a self-contained module with its own variables;
2. migrate recovery SAFE_WAIT continuation/relaxation/verified re-enable flow;
3. preserve the already-fixed two-phase `SAFE_WAIT -> MAIN` commit rule;
4. remove any remaining historical scaffold ownership for this chain;
5. regression-test restart persistence, Output OFF proof, OVP/OCP/readback/enable failure handling and exact AGM stage restoration;
6. only after that proceed to MIX/final SAFE_WAIT/Storage.

Parallel architectural rule: every touched value must move to the variable file owned by its module with complete metadata. Do not create another shared constant bag.

UI remains an independent mandatory workstream. New/future screens and buttons must use modular `ScreenSpec`/`ButtonSpec`/`UIAction`/routing and application intents; do not add callbacks or hardware/controller imports to legacy UI handlers while charge migration proceeds.

#### Immediate handoff actions

1. Re-verify local `HEAD` and worktree cleanliness.
2. Push the two local functional commits plus this runbook checkpoint when GitHub connectivity is available.
3. Wait for exact-head Python 3.10/3.11/3.12 CI.
4. If CI is green, update ledger statuses for ERADICATION-01 and MAIN ERADICATION-02 accordingly.
5. Start ERADICATION-03 from the exact green head; do not re-audit or redesign MAIN.
6. Do not deploy VM104 until a separate production-validation instruction is given.


## 14.9 ERADICATION-03 checkpoint — 2026-10-04

This checkpoint supersedes the execution plan in section 14.8.

Authority before the boundary:

- migration branch: `refactor/v3-modular-legacy-eradication`;
- pre-boundary HEAD: `396b364b79816366380ee89d452256d1e0bacf08`;
- PR: `#29 Begin modular V3 legacy eradication`;
- exact-head GitHub Actions run `#1510` / `37141127400`: PASS on Python
  3.10, 3.11 and 3.12;
- isolated worktree was clean and local HEAD matched origin before mutation;
- dirty primary worktree `E:\CODEX\rd6018_bot` was not touched;
- production VM104 was not touched.

Functional recovery cutover commit:

`0f161a85a847d010ea6b7b860c065295145adf7a` — Migrate recovery chain to modular V3 authority

Canonical recovery owners:

- `runtime/charge/strategy/desulfation.py`;
- `runtime/charge/strategy/desulfation_variables.py`;
- `runtime/charge/strategy/recovery_safe_wait.py`;
- `runtime/charge/strategy/safe_wait_variables.py`;
- `runtime/charge/runtime/recovery_scaffold.py`.

The authoritative recovery chain is now:

`MAIN -> DESULFATION -> recovery SAFE_WAIT -> verified MAIN`.

For this chain, historical `ChargeController.tick()` is no longer the
execution/decision scaffold. Static regression tests patch the historical tick
to fail if either authoritative DESULFATION or recovery SAFE_WAIT reaches it.

DESULFATION owns its duration, base voltage, 0.02C current rule, minimum target
current and stage-specific OCP margin through module-local `VariableSpec`
declarations. SAFE_WAIT owns the relaxation margin and bounded timeout.

Recovery SAFE_WAIT continuation now persists and validates:

- exact source and next stage;
- target V/I;
- start time;
- session identity;
- session generation;
- recovery attempt;
- AGM stage index.

Persisted continuation state is not sufficient to enable Output. A fresh
physical Output OFF observation is required before the strategy may request a
re-enable transaction. The software stage remains SAFE_WAIT while the request
is pending. The existing execution transaction still owns the physical
program/readback/enable/readback sequence, and only its successful verified
acknowledgement may commit SAFE_WAIT -> MAIN.

When the active session has a durable MAIN Current Guard, that same return
transaction first requires fresh direct ESP Native Output=OFF, Iset and clear
R16 protection evidence, issues the existing verified-OFF operation, and
requires newer OFF callbacks before programming. It restores the Guard's
original bounded MAIN current (never above the accepted recipe or global
stage limit), verifies fresh Iset, atomically saves the new Guard segment with
the charge session, and only then enables Output. Numeric OCP is not a MAIN
Guard admission gate or setter; its original physical protection owner remains
unchanged. The new MAIN segment starts with zero accrued time and a fresh
30-minute Guard interval. If preflight reports Output ON, no V/I/OCP target
is issued. This is software behavior; it does not constitute node104 or
hardware validation.

A restart defect was found while adding the required regression: historical
restore reconstructed DESULFATION `stage_start_time` from Ah and could corrupt
the bounded two-hour active-stage budget. The migrated controller now restores
the exact persisted DESULFATION stage clock after the legacy compatibility
restore. Recovery attempt and AGM step also survive restart.

Validation after the functional cutover:

- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- focused recovery/runtime/architecture regressions: PASS, including restart,
  stale continuation, fresh-OFF gating, failed enable/readback, and
  no-duplicate-enable coverage;
- final full local suite: 1793 tests PASS, 2 skipped.

ERADICATION-03 is locally complete. The remaining final gate is exact-head
GitHub CI after this documentation checkpoint is pushed. After that, the next
exact boundary is ERADICATION-04:

`MIX -> finish evidence/hold -> final SAFE_WAIT -> verified Storage/DONE`.

Do not fold Manual/Custom, full safety/execution convergence, UI cutover or
composition cleanup into ERADICATION-04 unless a newly proven generic repository
defect makes a minimal fix unavoidable.

Production changed: NO.

Hardware commands sent: NO.


### 2026-10-04 ERADICATION-03 remote verification

Exact functional/documentation HEAD:
`39f8ab2ef143ce1092aab267d511114c58395ff0`.

GitHub Actions exact-head run `#1512` / `37147682685` completed PASS:

- Python 3.10: PASS;
- Python 3.11: PASS;
- Python 3.12: PASS.

PR #29 points to the exact verified branch head. ERADICATION-03 is closed as
remote-verified. Production VM104 was not touched and no hardware commands were
sent.

Next exact boundary:

`ERADICATION-04: MIX -> finish evidence/hold -> final SAFE_WAIT -> verified Storage/DONE`.

Do not fold Manual/Custom, UI migration, composition cleanup or unrelated
safety/execution convergence into this boundary.


## 14.10 ERADICATION-04 checkpoint — 2026-10-04

This checkpoint starts from the remote-verified ERADICATION-03 head:

- branch: `refactor/v3-modular-legacy-eradication`;
- pre-boundary HEAD: `81e15c03f501f669f304660712ca77e84f3afb29`;
- previous exact-head CI: run `#1512` / `37147682685`, PASS on Python
  3.10, 3.11 and 3.12;
- PR: `#29 Begin modular V3 legacy eradication`;
- isolated worktree: `E:\CODEX\rd6018_v3_modular`;
- dirty primary worktree `E:\CODEX\rd6018_bot`: not touched;
- production VM104: not touched.

Functional ERADICATION-04 commit:

`aecde476ccb65ae1aeeb086638d490cd9825992d` — Migrate MIX and final completion to modular V3 authority

The migrated automatic completion chain is now:

`MIX -> finish evidence/hold -> final SAFE_WAIT -> verified Storage/DONE`.

Canonical owners introduced/confirmed in this boundary:

- `runtime/charge/strategy/mix.py` — production MIX stage decision while
  preserving the existing reusable `MixPolicy` API;
- `runtime/charge/strategy/mix_variables.py` — MIX voltage/current targets,
  profile active-time limits and sticky finish-hold duration;
- `runtime/charge/runtime/mix_scaffold.py` — common runtime mechanics for MIX
  and final SAFE_WAIT without historical stage transitions;
- `runtime/charge/strategy/final_safe_wait.py` — final continuation validation,
  fresh-OFF gate and relaxation/timeout decision;
- `runtime/charge/strategy/storage.py` — managed Storage target;
- shared `runtime/charge/strategy/safe_wait_variables.py` remains the canonical
  SAFE_WAIT margin/timeout owner.

Production semantics preserved:

- CV MIX: Imin / Delta-I evidence;
- CC MIX: Vmax / Delta-V evidence;
- confirmed mode-specific evidence starts the sticky two-hour finish hold;
- active MIX authority: Ca/Ca 20 h, EFB 24 h, AGM 10 h;
- final completion enters SAFE_WAIT with Output OFF;
- Storage enable requires fresh physical Output OFF evidence;
- final continuation is session-bound by identity and generation;
- stale generation fails closed;
- software remains in SAFE_WAIT while Storage enable is pending;
- DONE commits only after the existing two-phase execution transaction verifies
  OVP/OCP/V/I programming and physical Output ON.

Historical reachability proof:

- authoritative MIX no longer calls historical `ChargeController.tick()`;
- authoritative final SAFE_WAIT no longer calls historical
  `ChargeController.tick()`;
- regression tests patch the historical tick to raise if either path reaches it;
- `super().tick()` remains only for Custom/non-migrated program-family paths.

During the cutover, three implementation defects were found and fixed without
changing accepted charge semantics:

1. the first draft replaced `runtime.charge.strategy.mix` wholesale and
   accidentally removed its public `MixPolicy` compatibility API; the public
   API was restored and the new production authority was appended;
2. a module-level import of `runtime.safety.variables` created a package cycle;
   the shared 12 A safety ceiling is now resolved lazily inside MIX target
   selection, with no duplicate value owner;
3. `ProductionChargeControllerV2._mix_limit_seconds()` still had an independent
   local limit mapping; runtime now delegates directly to
   `mix_max_active_seconds()`, while `V2_MIX_MAX_HOURS` remains only a
   compatibility mapping derived from the same `VariableSpec` defaults.

Validation on exact functional commit
`aecde476ccb65ae1aeeb086638d490cd9825992d`:

- focused MIX/final/recovery/Storage/Cooling/compatibility suites: PASS;
- new ERADICATION-04 architecture/hardening suite: 10/10 PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full local suite: **1803 tests PASS, 2 skipped**.

ERADICATION-04 is locally complete. The remaining gate is exact-head GitHub CI
after this documentation checkpoint is pushed. If Python 3.10/3.11/3.12 are all
green, close ERADICATION-04 as remote-verified and begin ERADICATION-05
(Manual/Custom). Do not fold UI migration, composition cleanup or broad
safety/execution convergence into that next boundary.

Production changed: NO.

Hardware commands sent: NO.


### 2026-10-04 ERADICATION-04 remote verification

Exact functional/documentation HEAD:
`8e4a8964fad4b3d14d2ef5c0aad1424214444dee`.

GitHub Actions exact-head run `#1516` / `37170224025` completed PASS:

- Python 3.10: PASS;
- Python 3.11: PASS;
- Python 3.12: PASS.

PR #29 points to the exact verified branch head. ERADICATION-04 is closed as
remote-verified. Production VM104 was not touched and no hardware commands were
sent.

Next exact boundary:

`ERADICATION-05: Manual/Custom`.

Manual remains a separate program family that may share safety/execution
mechanics but must not become an escape hatch back into the historical AUTO
FSM. Preserve accepted Manual/Custom semantics while extracting its own
strategy/runtime owner and restart/fail-closed contracts.


## 14.11 ERADICATION-05 checkpoint - 2026-10-04

Boundary: `ERADICATION-05: Manual/Custom`.

Pre-boundary remote-verified HEAD:
`c64eee457df3abe3a4e01a81d1464fb90b52a9fe`.

Functional code commit:
`c99f1180d7fbe38063c4f453083bd428ce646a62` — Retire historical Custom production authority.

Manual is not being reimplemented as a second AUTO path. The existing modular
Manual program remains the production owner:

- `manual_mode.py` owns Manual session/program semantics;
- `ProductionManualSessionManager` in `manual_runtime.py` owns the
  production runtime/authorization lifecycle;
- the five-step Custom UI now produces a typed `ManualUIIntent` and submits it
  through `ProductionManualUIRoute`;
- the route delegates only to `ProductionManualSessionManager.start(request)`;
  the retired live adapter and bootstrap monkeypatch are absent, and an
  uncomposed route fails closed without an actuator request.

Historical Custom production authority is retired:

- `ManagedChargeController.start(PROFILE_CUSTOM,...)` is rejected;
- `ManagedChargeController.start_custom(...)` no longer exists;
- an active historical Custom residue is never allowed into
  `ChargeController.tick()`; it is forced OFF and the stale controller
  session is cleared;
- an IDLE Custom residue is inert;
- persisted historical Custom sessions are rejected on restore and require
  explicit operator reauthorization through Manual;
- the controller has no runtime authority switch and no characterization-only
  fallback owner; modular authority is unconditional.

Accepted Manual semantics were preserved, including the five-step Custom UI
payload mapping for voltage, current, Delta, active-time limit and capacity.
The typed route retains the wizard's 12–17 V, 0.1–12 A, Delta, 72-hour and
10–300 Ah validation boundaries before the canonical Manual transaction.
Existing Manual restart/re-authorization, cooling, verified-enable, stop and
fail-closed contracts remain owned by the Manual runtime.

Validation on exact functional commit
`c99f1180d7fbe38063c4f453083bd428ce646a62`:

- ERADICATION-05 architecture/fail-closed regressions: 8/8 PASS;
- start-route isolation: 8/8 PASS;
- recovery trace identity: 3/3 PASS;
- legacy enable inventory: 2/2 PASS;
- Manual runtime: 14/14 PASS;
- Manual mode: 7/7 PASS;
- Manual profile: 5/5 PASS;
- Manual context: 4/4 PASS;
- AUTO/manual-off: 4/4 PASS;
- modular Manual program: 5/5 PASS;
- Manual mode boundary: 3/3 PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full local suite: **1812 tests PASS, 2 skipped**.

ERADICATION-05 is locally complete. Remaining gate:

`docs checkpoint -> push -> exact-head GitHub CI (3.10/3.11/3.12)`.

On CI PASS, close ERADICATION-05 as remote-verified and continue with
`ERADICATION-06: safety and execution convergence`. Do not fold UI migration
or composition-root cleanup into ERADICATION-06 unless required by a proven
execution/safety ownership defect.

Production changed: NO.

Hardware commands sent: NO.


### 2026-10-04 ERADICATION-05 remote verification

Exact functional/documentation HEAD:
`ff75a060bb882546a87b6436f80da082731a5573`.

GitHub Actions exact-head run `#1520` / `37172114417` completed PASS:

- Python 3.10: PASS;
- Python 3.11: PASS;
- Python 3.12: PASS.

PR #29 points to the verified ERADICATION-05 branch head. Manual/Custom is
closed as remote-verified. Production VM104 was not touched and no hardware
commands were sent.

Next exact boundary:

`ERADICATION-06: safety and execution convergence`.

Gate: static production scan must find no physical writes outside the approved
physical execution implementation. Preserve current safety semantics, verified
OFF/ON ordering, readback verification, containment and lease behavior. Do not
fold UI migration or composition-root cleanup into this boundary unless a
proven execution/safety ownership defect requires the minimal dependency move.


## 14.12 ERADICATION-06 checkpoint - 2026-10-04

Boundary: `ERADICATION-06: safety and execution convergence`.

Pre-boundary remote-verified head:
`373325b82cbdbb5617a038ef1ac5bbd7287139a4`
(ERADICATION-05, GitHub Actions run `#1522` / `37172231948`, Python
3.10/3.11/3.12 PASS).

Exact local code HEAD:
`c63f75659d1809c34ba753b7045eb119ec0106c0`.

The live execution graph now has one application execution owner. START,
Mix-only START, Manual, controller action batches, operator output controls,
restart/lifecycle restore, link recovery, diagnostic recovery/probes and managed
adoption OFF all route through `application/execution_port.py`.

Static production scan gate:

- direct physical calls in the live graph are confined to the approved physical
  implementation:
  `application/execution_port.py`, `hass_api.py`, `runtime_safety_strict.py`,
  `managed_runtime_safety.py`, `safe_output.py`;
- `recipe_output.py` and `recovery_orchestrator.py` are quarantined historical
  compatibility modules and have no production inbound import edge;
- tests fail if a migrated runtime/application owner regains direct
  `set_voltage`, `set_current`, `set_ovp`, `set_ocp`, `turn_on`, `turn_off`
  or `safe_enable_output` authority.

Safety convergence:

- PB automatic voltage ceiling has one owner in
  `runtime/safety/voltage_variables.py`;
- MIX target/authority values have one owner in
  `runtime/charge/strategy/mix_variables.py`;
- historical compatibility surfaces derive those values rather than owning
  duplicate constants;
- typed safety decisions remain in `runtime/safety/engine.py`;
- verified OFF/ON ordering, readback verification, containment and edge-safety
  lease behavior are preserved.

Local validation on exact code HEAD `c63f75659d1809c34ba753b7045eb119ec0106c0`:

- focused execution/safety suites: PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- full CI-equivalent unittest discovery: **1830 PASS, 2 skipped**.

Production VM104 was not touched. No hardware commands were sent.

Remaining gate: commit this documentation checkpoint, push the branch, and
require exact-head GitHub CI PASS on Python 3.10/3.11/3.12. Only then mark
ERADICATION-06 remote-verified and begin `ERADICATION-07: UI cutover`.


### 2026-10-04 ERADICATION-06 remote verification

Exact functional/documentation HEAD:
`ab3ac72093fa1ee296334dfa1435138104ab1e1a`.

GitHub Actions exact-head run `#1524` / `37177596599` completed PASS:

- Python 3.10: PASS;
- Python 3.11: PASS;
- Python 3.12: PASS.

PR #29 points to the verified ERADICATION-06 branch head. The static production
execution gate is closed: live physical writes are confined to the approved
execution/physical implementation stack, while quarantined recovery
compatibility modules remain unreachable from the production graph.

## 2026-11-03 — Current recipe migration and active handoff

The current, continuously maintained execution handoff is
`docs/assistant/RD6018_CURRENT_CHECKPOINT.md`. Read it **first** for current
recipe migration status, exact deployed-vs-local code, test evidence, node104
hands_off state, and next tasks. Older sections of this historical runbook
record prior architecture and acceptance; they are not necessarily current.

Migration canon: existing native stage owners MAIN / Recovery / MIX / SAFE_WAIT
remain the only charge algorithms; versioned native copies carry validated
parameter overrides and an immutable session snapshot in the canonical atomic
charge_session.json. Unpinned AUTO and separate user SET/OFF recipes retain
existing behavior. Dynamic Recovery and SAFE_WAIT parameter wiring is still
pending. The visual editor prototype at
`tools/recipe_visual_editor_prototype.html` is retained but deferred.

**Documentation procedure:** for each completed RD6018 implementation stage,
update the current checkpoint **in the same stage/commit**. State exactly what
was changed, what tests passed or failed, which files are deployed, and which
remain local. Change this project runbook whenever ownership/canon changes.
Never conflate repository-level tests with physical evidence.

## 2026-11-05 — EFB Recovery adaptive plateau integration candidate

Canonical stage ownership remains single: MAIN tick measures, `main_authority`
selects existing DESULFATION/MIX effect, SafetyEngine and existing stage
recipes own actuation. Recovery plateau policy (90–120 min, bounded history)
is only enabled through an explicitly pinned EFB Recovery/Conditioning
native recipe; unpinned mode retains existing behavior. Configurable metadata
lives in `runtime/charge/evidence/recovery_plateau_variables.py`.
No separate charge loop, no change to AGM or Normal, and no claim of
electrochemical bank equality from voltage/current plateau alone. Source
candidate is not deployed to node104; full acceptance pending. Details and
tests in `docs/assistant/RECOVERY_ADAPTIVE_PLATEAU_2026-11-05.md`.

## 2026-11-05 — EFB Recovery MAIN→MIX guard-journal defect

Node104 read-only evidence confirms a physical incident during the existing
EFB 65 Ah Recovery charge: on 09:35:08 UTC MAIN completed its legacy
three-hour low-current tail and switched directly to final MIX; the canonical
guarded session writer rejected the new stage with
`ineligible_charge_stage`, followed by emergency verified OFF and edge
lease disarm. This was not caused by the new 90–120 minute plateau code,
which has not been installed on node104. Stale MAIN session is retained,
Guard revision 481, pending=False, fault=False. Direct guarded resume is
not authorized by the mere presence of a service or JSON session.

The source-only candidate allows an existing validated/revisioned MAIN Guard
journal to persist through the canonical atomic MAIN→MIX transition while
forbidding a newly created MIX Guard, unresolved pending proposal or silent
journal deletion. No alternate serializer, safety owner, or actuator is
introduced. It is compatible with the single-owner design. Production
deployment/physical activation are still outstanding; see
`docs/assistant/RD6018_MAIN_MIX_GUARD_HANDOFF_2026-11-05.md`.

**Offline acceptance checkpoint (2026-11-05):** source SHA `372f4ea`
completed exact-archive Linux full suite **2,888 PASS, 10 skipped,
1,673 subtests PASS, 0 FAIL**, with all 1,352 release-manifest files
verified. This validates the source candidate only; node104 remained
unchanged and current guarded charge session was not resumed.

## 2026-11-05 node104 deployment admission hold

The exact offline-tested release `372f4ea81c63fae20700eca85bbfa2aed8991ee9`
is staged but **not installed**. A fresh direct Native D148/D091 observation
before and after a read-only D145 prepare attempt showed R18 OFF and measured
U/I zero, with lease disarmed and boot quarantine false; HA agreed. The bot
remained active PID 213548, NRestarts=0. No service lifecycle or physical
actuator operation occurred. The D148 projection does not include all required
physical fields (R16, Vset/Iset, OVP/OCP, battery voltage, lease generation,
remaining time, Modbus age and complete trip/autonomous flags); do not call
this a complete deployment preflight.

D145 prepare refused before candidate admission because D137 requires a
retired session matching durable verified-OFF identity, while node104 retains
the active guarded EFB 65 Ah Recovery MAIN session. The failure was
`durable retirement and verified-OFF identity do not agree`; no state was
changed. Existing D090 remains `STARTED` without `candidate_inventory` and
`.deploy_sha` remains `58321a866dd68195bf8264d1d9ebe7c18a60748f`. A separate
existing D144 journal is already `COMMITTED` for source
`9a1f5ea4784dc37b19156c462e36c3b4a3de81c9`; preserve it. Installed D145 and
its D146/D147/D148 pins are historical and do not authorize the staged
`372f4ea` release. Do not retire or rewrite the guarded session to satisfy
admission, and do not replace release pins without a complete regression.
Deployment is blocked pending a reviewed admission path that preserves the
exact active session, the existing transaction journals, and complete fresh
Native physical evidence. No automatic resume is authorized.


## 2026-11-05 — guarded MAIN software-release admission under D142

D142 now obtains and validates a new D091 Native/HA physical OFF proof before
D137 reads the persisted preimage. An active guarded MAIN snapshot whose sealed
Guard records historical `last_output_on=true` is admitted only when the same
D091 proof is fresh, belongs to the current service PID, reports Native and HA
R18 OFF with zero U/I, the edge lease disarmed, boot quarantine clear, exactly
one physical node owner, and distinct source nonces. D137 binds that proof into
the observed preimage digest and keeps the original session/quarantine/journal
bytes, Guard hash, session/battery identity, revision, capacity, pending/fault,
and MAIN-stage checks. No persisted value is rewritten.

The deployed startup recovery path still treats Guard restore as OFF-only: it
requires a new direct Native pre-ON assessment and positively armed lease
before reconciliation, and `ExecutionPort` latches ordinary Output enable
until a distinct one-use physical-resume permit is consumed. With the observed
lease disarmed, automatic resume is blocked. This software-only install does
not authorize START or setpoint writes.

Fresh node104 observations on 2026-11-05 at 13:15–13:20 UTC, before any service
operation: service PID 213548; Native identity `timspb.rd6018-pb-recovery-v2`,
version `2.3-ha-canonical`, device 0; R18=0, measured U/I=0/0, battery
12.94 V, Vset/Iset=14.82 V/1.23 A, R16=0, OVP/OCP=16.70 V/12.0 A,
autonomous=false, lease armed=false/generation 61/remaining 0 s/TTL 900 s,
trip=false, boot quarantine=false, Modbus age 5.445 s. Native callback ages
were below 1 s in the detailed subscription; the independent D091 proof was
separately fresh and valid. HA readbacks agreed. These are pre-change
observations, not post-deployment evidence.

Focused software regression: **103 PASS, 34 subtests PASS** across D137–D145,
D149, startup Guard admission and pre-ON assessment. `compileall` passed. The
first ambient full-suite attempt was interrupted without a result; the isolated
full suite then stopped at the pre-existing D061 exact-source manifest pin
under the Windows-translated checkout. No node service, session, D090/D144
journal, RD Output, setpoint or lease was changed. Production D145 remains
blocked until the exact source-paired D145 profile and D138 tree/Python 3.11
stage are prepared and the canonical owner accepts a fresh prepare.

## 2026-11-05 — D145 static app pin versus fresh D137 identity

The release path had incorrectly compared D137's per-observation composite
digest (which includes the new D091 timestamp and source nonces) to D145's
static `preimage_inventory_sha256` (the installed `app/` byte inventory).
These have different lifetimes and meanings. D142 now carries the fresh D137
digest into D138 and the candidate identity; D144 validates the static
installed-app inventory after D091 has independently passed. No profile pin,
guard/session data, or historical transaction was rewritten. Focused D137,
D138, D142 and D144 checks pass (40 tests, 5 subtests); `compileall` passes.
This is a local implementation stage only; candidate packaging and node
admission have not yet been attempted.

D137's stable durable identity digest excludes only the transient D091 proof
(timestamp and source nonces); D142 still validates that proof before D137,
returns it as evidence, and D144 re-collects physical proof for each phase.
This lets the exact candidate identity remain the same across prepare/execute
while preserving fresh per-phase OFF evidence.

## 2026-11-05 — use pinned D148 for guarded-session prepare

The exact external D145 prepare reached D137 with a fresh OFF proof but D147
reported `active_session=false` while the persisted MAIN session remained
active. D148, already pinned by D145/D149 for the D144 state-preserving phases,
reports this same guarded session as active while preserving fresh Native/HA
OFF evidence. D145 prepare and execute now select that existing pinned D148
collector; D147 stays pinned and unchanged. No session/journal bytes changed.
Focused D137/D142/D144/D145 checks pass (45 tests, 5 subtests); complete exact
archive suite and a D145 prepare through D148 are pending.

The first two D145 prepares passed the D148/D137 guarded-state gate but
produced different D138 candidate IDs because D138 copied transient D091
nonces/timestamp into its durable identity payload. D138 now excludes only that
subrecord from the candidate identity digest while returning it in evidence;
source/venv inventory and durable guarded session identity remain included.
Focused D137/D138/D142/D144/D145 suite passes (51 tests, 5 subtests); exact
archive suite and repeated prepare identity equality remain pending.

## 2026-11-05 — exact D145/D138 candidate admitted for same-owner execution

Exact software source commit `d2aa2a53b8423292ba3abbbdd3261a73f6b2089a` was
packaged from its Git archive and staged under `/tmp` on node104 with a
Python 3.11.2 venv; source archive SHA256 is
`68e35a1ec0819fa113aa347dea8b0d1e03f71a16fd9008c6cc4b19f12ea21c0c`, and the
D138 source-manifest SHA256 is
`f93737d9a5cb5eba2623956e28fad79e9668cc1d04b8253c86525f1f7792abb2`. All 1,352
source entries match and `pip check` is clean. The new external D145 profile
pins the measured installed app inventory and exact source/manifest bytes;
the historical d351 profile file was not edited.

The exact archive full suite passed **2,904 tests, 9 skipped, 1 archive-only
fixture deselected, 1,677 subtests passed**; compileall passed. Repeated D145
prepare through the same D090 lock and pinned D148 reader passed and returned
the same candidate identity
`39407c15c850ecaeff1e8d2261c7d989b8b5be6ab2d4be9bd4307ab69e5af976` on each
fresh D091 proof. The preserved MAIN Guard is rev481 with historical
`last_output_on=true`; `automatic_resume_authorized=false`. D144 slot 2 backup,
journal, candidate and old-component paths were all absent before execution.
No service stop or actuator change has occurred yet.

Deployment attempt on 2026-11-06 stopped before D145 execute. Fresh direct ESP
Native data passed identity, freshness and OFF/zero checks (R18 OFF, U/I zero,
lease disarmed, generation 61, remaining 0, trip/quarantine/autonomous false),
but the independent fresh D091 Native+HA collector failed with
`ProofError: ESPHome device identity/project does not match reviewed node`.
No production files, service state, D090/D144 journal, Guard/session, or
actuator state were changed. Resolve the installed collector's identity
configuration and obtain a new D091 pass before attempting the same staged
D145 executor. The detailed physical evidence and exact candidate/test hashes
are recorded in `docs/assistant/RD6018_CURRENT_CHECKPOINT.md`.


## 2026-11-06 — D145 firmware environment verified; cutover did not commit

Correction/continuation of the preceding attempt: the exact D145/D142 path
sets `D090_EXPECTED_ESP_VERSION=2.3-ha-canonical` before launching D091, and
D149 sets the same value for its phase-specific D147/D148 reads. D142 also
sets software-release and state-preserving-recovery mode. The D091 collector's
`2.2-autonomous-authority` fallback is reached only when a caller omits that
environment variable. Running the exact staged D145 `prepare` with its source
tree on `PYTHONPATH` passed fresh D091, D137 and D138 and returned the unchanged
candidate identity `39407c15c850ecaeff1e8d2261c7d989b8b5be6ab2d4be9bd4307ab69e5af976`.
The previous D091 project/version refusal was not reproduced on this actual
D145 path. A first launcher attempt did not reach D091 because its import path
was incomplete. A later attempt added 39 `__pycache__` files to the temporary
source stage; those files were removed, and subsequent invocations used
`PYTHONDONTWRITEBYTECODE=1`. The staged source manifest then passed.

The authorized D145 execute started the candidate and wrote append-only
`D144_TRANSACTION_2.json`, but did not reach COMMITTED or create
`D144_INSTALLED_RELEASE_2.json`. The command output was not captured, so the
exact execute exception is unavailable. Durable state is transaction
`d8660aa810f04c75aed679f1f3aa4cb1`, phase `STARTED`, source
`d2aa2a53b8423292ba3abbbdd3261a73f6b2089a`. Fresh post-start D091 and direct
ESP Native observations reported Output OFF. The app/venv candidate inventory
was exact at that point.

The same source-paired D145 recovery command ran under the canonical D090 lock.
It restored app and venv byte-for-byte to the transaction's original preimage
and restarted the previous service, but returned
`TransitionError: restored service not stable`. A later read reported the old
service stable (`_stable_process` true) after readiness logs appeared. Since
the one-shot recovery check had already failed, D144 slot 2 remains `STARTED`
and its backup remains. Do not edit this journal or claim a completed
deployment. Current app/venv match the D144 preimage, service is active at PID
218804 with NRestarts=0, and the previous-source marker is
`58321a866dd68195bf8264d1d9ebe7c18a60748f`.

Fresh final direct Native subscription at 2026-11-05 17:11:11 UTC identified
`timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, `rd6018-controller`,
`esp01_1m`, device 0. Callback ages were <=0.56 s: R18=0, measured U/I=0/0,
battery=12.90 V, Vset/Iset=14.82/1.23 V, OVP/OCP=16.70/12.0, R16=0,
autonomous=false, lease armed=false/generation=61/remaining=0/TTL=900,
trip/quarantine=false, Modbus age=5.006 s. Independent D091 at 17:11:14 UTC
reported Native and HA Output OFF, 0 V/0 A, fresh Native state, lease
disarmed, clear quarantine, active guarded session and service PID 218804.
The EFB 65 Ah Recovery MAIN session/revision 481 remained byte-identical
(session SHA256 `b433bd304d22873dcdc5e3402386ca1c78a2b4ba141c8d241fc0dc7cdbac665a`).
Historical D090 `STARTED` remains byte-identical (SHA256
`030f0b7aae43402f523bb57f5acd606e3ab2fe4f7c7d4efd40258b40bde8014e`), and
the earlier D144 slot 1 COMMITTED record remains byte-identical (SHA256
`b8b64fd8b95261ba80528aa13e838fd5b3085f46a70ceb7371746c932b35a08a`). D144
slot 2 SHA256 is `e864c72a8ddb2270776c0457557a4e5c0a1138fc24c8ebe5d37506cda43666e1`.

Deployment result: **not committed**. The D091 version environment is verified.
D144 slot 2 is incomplete; the execute exception was not captured, so its
failure point is unknown. Recovery returned the exact one-shot error
`restored service not stable`; the prior service later became stable, but the
owner has no safe resume/commit path for this unfinished ledger. Do not rerun
execute or manually advance it. Next work must review and test bounded
post-start readiness handling in the existing D145 owner, then settle slot 2
only through the same owner. No charger START, Output ON, setpoint write, lease
write, session edit, D090 edit, or prior D144 slot 1 edit occurred.

## 2026-11-06 — D090/D144 bounded service readiness

The owner readiness predicate now waits up to 120 seconds after systemd start
and requires an active service, stable positive MainPID, exactly one matching
`bot.py` process, `NRestarts=0`, a current-start `ActiveEnterTimestamp`-bounded
journal containing the actual polling-ready message, and no startup fault. The
same bounded predicate is used by D144 for candidate acceptance and rollback /
recovery acceptance. Timeout, service exit, PID change, duplicate owner, or
startup faults fail closed. Focused offline tests passed 38 cases; full suite
and compile evidence are recorded in the current checkpoint when complete.
This is software owner behavior only and authorizes no physical charging action.

Node104 deployment remains held: the local readiness fix is not installed in
the external D090 owner, D144 slot 2 is still `STARTED`, and the previous
release remains active. The latest complete direct Native/D091 + D148 evidence
confirmed R18 OFF, measured U/I zero and lease disarmed, but detailed D106
read-only collection failed closed on Native entity type mismatches, and D091
reported the preserved guarded session inactive. Therefore recovery lacks the
full fresh physical field set and trustworthy guarded-session proof required
for D145. No recovery/execute was invoked. Do not claim d2aa installed or slot
2 settled. Full archive regression has no valid PASS yet; see current checkpoint.

## 2026-11-06 — slot-2 recovery complete; bounded release preparation next

The D145 recovery for D144 slot 2 completed under the existing D090 owner lock
using the committed 120-second current-start-epoch readiness implementation.
Slot 2 is `RESTORED` with its original app/venv preimage verified; its exact
journal SHA256 is recorded in the active checkpoint. Node104 still runs the
previous `.deploy_sha` `58321a866dd68195bf8264d1d9ebe7c18a60748f`, MainPID
219592, active, `NRestarts=0`.

Fresh direct ESP Native typed callbacks identified device 0 as
`timspb.rd6018-pb-recovery-v2` / `2.3-ha-canonical`, with R18 OFF, measured
U/I zero, R16 clear, lease disarmed/generation 61/remaining 0, trip and
quarantine clear, autonomous false, and recent Modbus age 0.703 s. Independent
D148 Native+HA evidence confirmed OFF, zero current, one physical owner, and
the existing guarded EFB Recovery MAIN session active. That session checksum,
historical D090 STARTED, and D144 slot 1 COMMITTED remain unchanged. The
software-only admission uses the approved Native/HA output/current and edge
containment facts; it does not require analog output-voltage, programmed
setpoint, OVP/OCP or autonomous-mode readbacks.

The bounded-readiness code is still local production source; the recovery
runner used its exact committed owner modules only in temporary `/tmp`
execution staging. No application update has been committed on node104. Next
is to stage the exact `beab527c2f5413962d3bccd8c140f3a0417dca17` source and
Python 3.11 environment, create the matching D146 profile, pass D145
prepare-only, and execute the same-owner D144 transaction after another fresh
Native + D148 OFF observation. No START, Output enable, setpoint, or lease
write is authorized or planned.

## 2026-11-06 — beab source/profile prepared locally

An exact source-only D138 package is prepared locally for the committed
bounded-readiness source `beab527c2f5413962d3bccd8c140f3a0417dca17`: 1,352
files, archive SHA256
`c4710ee5e77317b25bb0ceb34b0c05b9d44b49b442d1cb3bbdd72ecc2adfa658`, and
manifest SHA256
`3ded71cbc7fe906985d60fbfef9fca9e4045ad388369381b34ddb8bc39af8183`.
Its D146 profile pins the restored app preimage and is committed alongside
this checkpoint. It is not yet on node104. The installed `.deploy_sha` remains
`58321a866dd68195bf8264d1d9ebe7c18a60748f`; slot 2 remains RESTORED. Next
work is same-owner D145 prepare with a staged Python 3.11 environment, followed
by the normal D144 transaction after a fresh direct Native and D148 OFF proof.

## 2026-11-06 — software-release proof excludes cancelled readbacks

The previous beab profile was superseded before transfer after review found
that the shared D091/D142/D137 pre-stop proof still made voltage and
autonomous-mode entity identity mandatory for software-only release. Code
commit `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e` scopes those fields out only
when `D090_SOFTWARE_RELEASE=1`: fresh typed Native and HA R18/current remain
required, along with the existing D090 owner, edge containment, service,
session-integrity and source-identity checks. General D091 validation keeps
its existing physical voltage and autonomous-mode checks. Guarded MAIN
reconciliation now validates current zero and OFF identity without relying on
an analog voltage readback.

The target source is now exactly 9d1aa; the earlier beab candidate was never
transferred. Focused checks passed 59 tests with 1 skipped across D091, D142,
D137 and D090 release validation; targeted `py_compile` and `git diff --check`
passed. Node104 remains on the prior 58321a release, service PID 219592,
`NRestarts=0`; D144 slot 2 is RESTORED. Next stage a Python 3.11 candidate and
matching profile for 9d1aa, then follow same-owner D145 prepare and execute
with fresh direct Native and D148 proof. No START, Output ON, setpoint or lease
write is authorized.

## 2026-11-06 — exact 9d1aa source/profile prepared locally

The target source is now `9d1aa22243904bc7f9b80f2ae128fc7fc48e193e`; the
superseded beab profile was removed before transfer. The exact 1,352-file D138
archive SHA256 is
`7a88f39e866405b76760fe0c4ae671aa91f4be86e8c577eb9e6e1fa6593ff663`; its
manifest SHA256 is
`da04dd3b68fee2e8566ad6140fade2636d1c476d9bf6b890a90efea8888b3de5`. The
source-paired D146 profile SHA256 is
`1c55477e693441880b1acfa31d5c2981cfaa775376b080863953d8295aab699a`. This
package is local only. Node104 remains on 58321a with D144 slot 2 RESTORED and
service PID 219592. Next, stage the exact archive and the validated Python
3.11 dependency environment in `/tmp`, then run same-owner D145 prepare. Take
fresh direct Native and D148 OFF/session evidence again before execute. No
START, Output enable, setpoint or lease write is authorized.

## 2026-11-07 — installed baseline, cleanup and adaptive-data roadmap

**Current node104 production baseline:** source commit `384516decb4b44e1cb9324fcf820b23ed445d593`, D144 slot 11 `COMMITTED`. The previous release was `1beb4e1` (slot 10). Both deployments were software-only through existing D145/D144 owner; node104's original D090 historical ledger was preserved. For exact transaction, test and historical Native/HA OFF evidence see `docs/assistant/RD6018_CURRENT_CHECKPOINT.md`. Never use older dated sections of this chronological runbook as current runtime state.

**Active behavior:** normal AUTO START prepares V/I, clears previous-session non-requested positive hardware OVP/OCP while Output is independently OFF and confirms V2 readback, before Output ON; RD60xx 0 means protection threshold disabled, not a zero ceiling. Explicit recipe-owned limits (e.g. MIX) remain, and physical hardware trip R16, absolute/recipe U/I bounds, temperature, verified OFF and 900 s edge lease remain mandatory. Idle graceful shutdown is bounded. These fixes were source-tested and installed; a successful entire START→MAIN→MIX→STOP physical cycle is not established by the deployment tests alone.

**Measurement work is deliberate, not incidental:** continue recording real EFB/Ca-Ca charge traces (U/I, setpoints, CC/CV, temperature, stage transitions, Imin, STOP causes) and post-OFF voltage relaxation via the separately deployed passive D063 observer. D063 does not drive hardware and only collects when a suitable SAFE_WAIT session exists. Record missingness and time alignment before fitting an adaptive charge-control policy. Keep the current deterministic charger behavior until quality and repeatability justify a bounded adaptation; AGM behavior remains governed by the already-approved recipe.

**node104 cleanup:** the operator requested only the working application, not historical deployment duplication. 226 obsolete staging/backup/probe items were deleted after inventory, releasing about 4.7 GB. Preserved active `app`, `venv`, `.env`, `state` (including measurement SQLite and charge session), `optional/voltage_relaxation`, canonical D090/D144 ledgers, installed-release identity, `d147-proof`, `logs`, `backups`. After cleanup bot and D063 remained active with zero service restarts; an operator-started EFB 80 Ah MAIN session continued. Cleanup did not interrupt Output or change setpoints. Timestamped observations do not establish current charge state.

**Next owner priorities:** (1) inspect existing EFB 80 Ah MAIN/STOP event stream and eliminate verified charge execution defects; (2) resolve genuine watchdog blocking and Telegram graph/HMI defects using the existing owners; (3) accumulate valid D063 relaxation sequences; (4) introduce adaptive EFB/Ca-Ca decisions only after data analysis and existing safety bounds. No new independent control mechanism or artificial acceptance gates. Wake Bridge R7.2/R8 and PCP/Balansir are separate projects.

## 2026-11-07 — Telegram UI source-only navigation repair

The canonical Telegram panel remains graph-backed; journal/menu/detail callbacks must not replace its dashboard identity. Restore last graph/control panel after navigation, while journal events use bounded, paged, separately tracked messages. Deferred refresh is generation-cancelled on navigation. See docs/assistant/RD6018_CURRENT_CHECKPOINT.md for offline tests and deployment gate. Not installed on node104.
## 2026-11-07 — journal event-loop isolation follow-up

Canonical Telegram journal events now load through the existing `EventJournalReadService.aread()` async boundary; callback errors are visible and pages respect Telegram payload limits. The callback acceptance test fixture no longer routes synthetic selections into real Telegram sends or cancels unrelated event-loop tasks. Source-only, not installed on node104; details and verification limits in docs/assistant/RD6018_CURRENT_CHECKPOINT.md.
## 2026-11-07 — charging journal real session start boundary

`SESSION_START` remains the authoritative event-log session boundary even when the same production START later logs `V2_START | PREP_SKIPPED...`. `V2_START` alone is a legacy fallback boundary. This fixes the Telegram journal appearing to contain only PREP_SKIPPED. See checkpoint for regression evidence; source not yet installed on node104.

## 2026-11-07 — Telegram UI callback fixture and stale journal pages

The callback acceptance fixture now replaces `_refresh_operator_panel` at the UI/snapshot boundary so synthetic navigation does not read production ESP128 configuration or conceal provider errors. Journal rendering clamps an expired or forged page offset to the oldest remaining event, preventing an invalid `1–0` range. These are source/tests only; node104, Telegram, and the PSU were not accessed. See `docs/assistant/RD6018_CURRENT_CHECKPOINT.md` for exact verification limits.

## 2026-11-07 — MIX CV operator status label

MIX CV `Imin` age is elapsed time since the accepted current minimum, not a countdown to finish. Only confirmed Delta I starts the separate sticky finish hold (default 2 h), followed by SAFE_WAIT after ordinary policy checks. Telegram HMI labels interval as elapsed and waiting Delta I; MAIN countdown is unchanged. Source-only; see checkpoint.
## 2026-11-07 — Telegram MIX extrema/Delta/hold statuses

Read-only MIX HMI now shows: CV searching Imin -> accepted Imin plus measured/required Delta I, CC searching Vmax -> accepted Vmax plus measured/required Delta V, then confirmed Delta -> pinned finish-hold countdown to SAFE_WAIT. All evidence comes from existing `ui_support_snapshot()` and canonical hold start, with missing evidence explicitly displayed. UI-only; no physical deployment or new owner. See current checkpoint for tests.
## 2026-11-07 — achievable MIX CV Delta

MIX CV current reversal target is 30% above accepted Imin, bounded by the existing phase current setpoint. Analyzer threshold remains >=0.03A resolution floor; if headroom is smaller, do not assert Delta evidence. Existing CV/CC, thermal and timing gates still govern. Example 2.18A minimum and 2.40A cap => +0.22A threshold, not +0.654A. Do not raise PSU current to force evidence. Runtime change is source-only, not installed on node104; details/tests in checkpoint.

## 2026-11-07 — D137 release admission repair (source-only)

D137 now permits an absent legacy `.deploy_sha` only when the latest contiguous
D144 slot is `COMMITTED`, its `D144_INSTALLED_RELEASE_n.json` identity names
the same transaction and valid source/candidate digests, and its recorded app
and venv inventories exactly match the installed directories. Existing marker
validation remains unchanged when the marker is present. D090's historical
`STARTED` journal is observed and hash-pinned, never rewritten; no marker,
owner, or authorization is synthesized. The regression models the reported
slot-11 installation and rejects non-COMMITTED/inventory drift.

The current node104 facts in this source-only request are operator-provided
fresh D148 Native+HA evidence at 2026-11-07 01:33 UTC: Output OFF, 0 V/0 A,
lease disarmed, no active session, one owner. This timestamped evidence is not
a live observation by this edit and expires for any later operation. Installed
source remains `384516decb4b44e1cb9324fcf820b23ed445d593`, D144 slot 11
`COMMITTED`; local source base was `96a1fc294fc56de167f549d71156f82cd349b02a`
and `origin/main` matched it. Focused D137/D142/D144/D145 regression: 63 PASS.
No server access, service action, ESP command or deployment occurred.

Next release must use the existing D145/D090 owner. The tracked D145 entrypoint
and D146 profile are currently pinned to source `d351c208…`; do not use them
unchanged. After this change is committed, build an exact D138 stage from that
commit, prepare the matching Python 3.11 venv, generate and review a new D146
profile for the committed source and observed D137 preimage, and update only
the source-paired entrypoint/profile pins. After STOP/session confirmation and
a new complete direct ESP Native preflight, run
`python3 tools/node104_d145_entrypoint.py prepare --profile <new-D146-profile> --stage <exact-D138-stage>`;
acquire a distinct fresh pre-execute Native proof, then run that command with
`execute`. Both phases use the existing D090 owner and lock. Keep D090
historical bytes and state unchanged; no D145/execute is authorized by this
source-only repair. The local commit is currently blocked because `.git` is
read-only (`.git/index.lock` creation failed); code HEAD remains
`96a1fc294fc56de167f549d71156f82cd349b02a`, equal to origin/main. Four intended
paths remain uncommitted; unrelated `.deploy_*` worktree files were preserved.

## 2026-11-07 — D145 cutover withheld due to newly active MAIN

Independent D148 initially confirmed OFF after operator STOP, but before D145 a new `SESSION_START` recorded `User Command`, and Native+HA later both confirmed Output ON and active lease in new MAIN. No D145 prepare/execute, service restart or actuation; source candidate 6ee72bb staged then its owned temporary files cleaned. Production remains 384516d D144 slot11. See checkpoint for times, evidence and release pin. Next release only after another fresh OFF and session reconciliation.
## 2026-11-07 — node104 LIVE release slot12 COMMITTED

Current node104 production release source is `85b70a1642e4dd5629d0f22d4a96ddc770bfed96` installed via the canonical D145/D144 transaction slot12 (`COMMITTED`), superseding earlier slot11 `384516d`. Includes Telegram dashboard/journal/MIX operator status and the bounded MIX CV current reversal (`min(1.3*Imin, current setpoint)`), plus canonical D137/D144 support for pruned historical records. Live D148 independent Native+HA OFF proof after cutover and cleanup: epoch 1794022576.0509691, both 0 V/0 A, lease disarmed, no active session, one owner. Bot active PID 229869, NRestarts 0, Telegram polling observed. Owned staging and duplicated release copies cleaned, durable D090/D144 history and all charge state/history preserved. See checkpoint for precise pins, tests, and limits of physical acceptance.
## 2026-11-07 — charge wizard remains last until START terminal action

Charge mode/profile/battery/intent and preview messages are workspace screens, not triggers to append the Idle panel. No UI module may manually send the dashboard during selection. Explicit START completion posts feedback first; the existing `TerminalPanelManager` restores the graph/control panel once, last in chat, through canonical `_restore_dashboard_to_bottom`. See checkpoint for regression tests and installed-version gate.
## 2026-11-07 — EFB intent/START Telegram panel hotfix release boundary

Source `bd54bd7` repairs unintended Idle panel appended under the charge wizard and guarantees one graph/control panel after START feedback. Production D144 slot12 remains at `85b70a1`: user started a fresh EFB80 MAIN on node104 at 13:38 local, D148 strict OFF gate fails, so do not interrupt the session to install a presentation-only update. Check checkpoint for tests, evidence, and next guarded release condition.
## 2026-11-07 — Native readback transient disconnect / V2 safety

EFB MAIN safety OFF at 04:09 UTC followed an actual Native API TCP reset (`Errno 104`) and partially unavailable canonical register callbacks, not a Telegram alert mistake. OFF verified by fresh physical R18 at 04:09:56. Native transport hotfix waits at most 8 s for genuine safety-critical callbacks *after reconnect only*, then hands any still missing/stale values to unchanged fail-closed guard. Missing raw R18 yields UNKNOWN, not fabricated OFF. Production not yet changed; restored output was independently checked OFF, saved MAIN session remains intact. See checkpoint for incident timeline, tests and separate historical ESP link resets.
## Native link 300s policy
2026-11-07 canonical: ESPHome Native link loss <=300s does not software-STOP. Single monotonic epoch across partial callbacks; hard safety, physical edge lease 900s, explicit STOP remain unchanged. Native partial read defers controller tick and hardware watchdog; soft watchdog 360s covers polling skew. 72/72 offline tests pass. Source only until D145 production deployment; checkpoint has details.

## 2026-11-07 LIVE D144 slot13
2026-11-07 node104 LIVE deployment: D145 PREPARE_ONLY_PASS, D145 execute exit 0; D144 slot13 COMMITTED, installed exact 9692cf37abbb343faff1285b59b03bb668e4c36a, transaction 07a1d7ecce4744bbae5d6b1c328b0ec9. Pre- and post-deploy D148 independently verified ESP128+HA102 Output OFF, 0V 0A, lease disarmed, active_session=false, one owner. Post deployment epoch 1794027078.9520783; service active PID230509 NRestarts0; Telegram aiogram Start polling at 04:50:42 UTC and Run polling at 04:50:43 UTC. Five-minute outage handling is installed. A cleanup attempt of slot13 duplicate folders and owned D138 staging was denied by tool safety, so those copies remain untouched; no claim of full cleanup. Data history, secrets and active code intact. No physical charging test or auto-START.

## 2026-11-07 Monitoring and Telegram single-panel operator canon

Current accepted node104 slot13 9692cf37 was read-only checked at 15:56 stand local: EFB80 Recovery MAIN 14.77V,0.23A,26C; HA/Native Output ON match; edge lease armed/trip false; rd6018-bot and voltage-relaxation services active, zero restarts. Alert findings: 05:32 UTC Telegram panel edit not found / not modified warnings, no Native/safety fault. UI source repair uses PanelLastMiddleware as sole L2 restore owner across read-only screens and home navigation. Journal service rows filtered before pagination, 8 human one-line entries/screen; first and lower confirmed Imin MAIN and MIX Imin/Vmax go through existing action log_event_sub, not through extra analyzer, timer or service. Testing 105 V3 UI + 77 operator panel + compile PASS. Source-only, no production update while charge live. See assistant checkpoint for precise values and error lines.

## 2026-11-07 Graph U-I autoscale
Near-constant 0.23A and 14.76V traces were rendered on hard-coded 0..20 axes. Existing graphing.py now scales U/I to visible readings with proportional margin and minimum spans 0.30V / 0.10A; zero stays visible on all-zero data. Both 3-pane and dual-axis charts covered; temperature scaling unchanged. 69 related UI/graph tests PASS. Source only, no production restart during active charge.

## 2026-11-07 - Staged release pending post-charge
Source 034bcee34a5eb199d466f62ee18a640fd323dc88 staged and verified on node104 at /tmp/d138_stage_034bcee3, handoff RELEASE_HANDOFF.json; 1359 file hashes/modes PASS, pip check PASS, on-host graph tests 6/6 PASS. Production remains slot13 9692cf37 PID230509, no restart. After charge, physically verify OFF and no session, capture fresh D137 identity and issue D146 profile + D145 prepare/execute; do not use prior preimage pin. See assistant checkpoint for exact checksums and release procedure.

## 2026-11-07 node104 16:32 scheduled monitoring
EFB80 Recovery MAIN Output ON 14.77V 0.22A Native=HA, 26C latest checkpoint; lease armed 900s, no trip, no new readback/Native/watchdog errors; bot PID230509 and relaxation PID62502 both active, zero restarts. Full source evidence in docs/assistant/RD6018_CURRENT_CHECKPOINT.md. Telegram publisher module extraction remains local WIP, not deployed.

## 2026-11-07 Telegram UI one-publisher canon
2026-11-07 Telegram UI architecture: one polling process, but in-process parallel publishers caused duplicate panels. Introduced runtime/ui/telegram/panel_lifecycle.py as sole per-chat lifecycle owner: one current L2 ID, graph adoption/retirement, L3 workspace state, one asyncio lock shared by terminal publication and periodic graph edit, exactly one 60s graph refresh task. telegram_panel.py reduced to middleware/composition. operator_dashboard.py renderer no longer owns task/mutex, operator_hmi callbacks request owner edits. Deleted runtime/production_runtime.py old text dashboard and delayed 60s tasks with 15 calls, no no-op compatibility subsystem; Manual/START/MIX direct publishes removed; /start and notifications use owner. Source only; existing deployed node104 slot13 9692cf37 unchanged. Prior staged 034bcee3 does NOT contain this future UI refactor. Offline tests: 105 V3 UI PASS, 106 combined operator/panel/START/MIX PASS, 18 production/HMI PASS, 3 namespace PASS. Installed callback dispatch acceptance 5/5 PASS offline; live Telegram acceptance pending. No charging changes or node restart.

Final architecture audit: additionally deleted 44 lines of unused runtime.production_runtime._edit_or_send_charge_workspace, a dead L3 Telegram sender that wrote menu message IDs into user_dashboard/chat_dashboard L2 maps. Removed its two obsolete characterization tests; actual /start and panel middleware tests 23/23 PASS. Single active panel owner is unchanged. This is source-only and no production action.

## Telegram UI 60-second in-place refresh
The single panel_lifecycle owner schedules one 60-second graph refresh loop. On a new plotted sample operator_dashboard uses edit_message_media on the existing message ID; when no new graph point exists it still reads current HMI snapshot and uses edit_message_caption on the same message (including controls/countdown). Never send_photo or create a second panel for periodic refresh. Workspace navigation suppresses background edits. 43 targeted tests PASS; source-only pending completion of the full UI refactor. See checkpoint.
## 2026-11-07 ? Telegram UI single-owner closure and namespace scan fix

Single-owner source: panel_lifecycle owns per-chat panel ID, one per-chat lock, one 60-second graph refresher and workspace state. Telegram message IDs are chat-scoped, so a two-chat collision is handled by an explicit chat-to-user binding. Graph-range callbacks edit the same L2 and no longer suspend 60s updates; Manual v2_manual_unbound publishes via one terminal middleware path. Empty adopt callback branch removed. Tests of stale message replacement and real Telegram failure now exercise canonical panel owner rather than deleted legacy module. Namespace scanner uses os.walk with pruned .venv and archived worktrees instead of exhausting memory in rglob; namespace tests 3/3 PASS. V3 UI 105/105, panel/graph/navigation 49/49, START/MIX/Telegram dispatcher 28/28 PASS. Source only; no node104 operations. Earlier staged 034bcee3 is graph-only, NOT this future UI release.

## 2026-11-07 Paused D145 blocked
2026-11-07 paused-session deployment audit: D49 UI candidate staged and verified, but D142 read-only preflight fails D137 observed_preimage with guard_journal_absent, because active EFB Main Charge session does not contain main_current_guard_v1. OPERATOR_PAUSE_ON logged at stand-local 17:58:14. Independent HA and ESP Native: Output OFF 0V 0A; edge lease disarmed. Live active_session remains true. D145 prepare/execute NOT invoked, bot PID230509 remains on 9692cf37, no restart or physical writes. Do not fabricate guard or bypass state-preserving admission. Reconsider cutover after session retirement or safely validated guard provenance; stage d49cb6d1 intact.

## 2026-11-07 — Post-charge D49 deployment preflight and external execution block

Operator completed EFB80 charge: at 18:12:41 stand-local, charging history SESSION_STOP reason=operator_verified_auto_stop; state/charge_session.json no longer exists. Physical independent HA102/Native OFF and lease disarmed in last proof. node104 D142 read-only preflight on exact staged source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b returned PASS_AT_OBSERVATION_ONLY, capacity_pass=true, fresh_d091_off=true, preserved_guarded_main=false. Observed preimage SHA256 0aeef616075d386e8be1dda3c48553a37bf7c3671fb406723dd73d5a18584aed, candidate identity b9be5f6f9188991324372f07fbbfc7d3e9c0999678ecbe332b948d2621f0e981. Guard journal absent blocker disappeared with genuine retired session; no bypass or fabricated state.

D146 exact profile uploaded to /tmp/d138_stage_d49cb6d1/D146_D49_PROFILE.json (SHA256 ff676268e2ce9a5f663ab45280499a1e2971a99ad768cee20d16cc27bee72d0a), with installed app inventory 22e596ba048d9380d057418698c74d0810e5d17230a98cd16b91dd2e52dc8284, 44 changed paths, source and manifest SHA pins, systemd unit SHA 74146a925d8c80a6a240f78877e76e060e674f6928f748db43891e7ff1b0e068, environment SHA 374d4b0decee7d04d0f4358bdcb30a58737c5edd2d3f743cc65d10e56dabc6b3. Canonical profile-loader validation PASS. Existing D145 source-paired entrypoint pinned to these identity values uploaded to the same stage. No new deployment owner or mechanism.

EXECUTION BLOCKER: HOME-PC invocation of canonical D145 prepare was denied by tool safety system before starting. No D145 prepare or execute performed; no node104 restart or hardware operation. Last read-only node104 verification at 08:20 UTC: installed D144 slot13 source 9692cf37abbb343faff1285b59b03bb668e4c36a, service PID230509 NRestarts=0, no active session, 4.0GB free. Candidate stage and profile retained. Do not circumvent tool safety; when execution is authorized use existing D145 prepare then execute under same D090 owner and verify committed release, Telegram polling, Native/HA OFF, persisted data. No second publisher, no additional proof layers.

## 2026-11-07 D144 slot14 installed
2026-11-07 node104 D145/D144 deployment ACCEPTED at service and physical level. Owner retired EFB80 session first; charge_session.json absent. D145 prepare returned PREPARE_ONLY_PASS, fresh_d091_off=true, capacity_pass=true, preserved_guarded_main=false. D145 execute EXIT 0; D144_STATE_PRESERVING_V1 slot14 COMMITTED, transaction be4fce7576844e5c95df1ea8e6aeda15, source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b, candidate identity b9be5f6f9188991324372f07fbbfc7d3e9c0999678ecbe332b948d2621f0e981. New service PID231800 active from 08:41:27 UTC, NRestarts0, single bot.py polling process. aiogram Start polling and Run polling for bot @RD6018_bot logged 08:41:34 UTC; no active TelegramConflictError (startup INFO contains a generic conflict advisory). Voltage relaxation sidecar PID62502 active, zero restarts. Postflight D148 collect_live: ESP Native and HA independently Output OFF U0V I0A, safety lease disarmed, no trip/quarantine, active_session=false, TTL900s. Disk 3.5 GB free, 54 percent used. No hardware commands. Prior installed slot13 source 9692cf37. D49 stage and release profile retained. Operator navigation, journal formatting, and 60-second in-place message refresh still require live Telegram interaction acceptance, not established by polling.

## 2026-11-07 — MAIN to MIX countdown display polish on frozen UI baseline

Baseline frozen BEFORE modifications. Exact known-good installed UI source d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b is protected by immutable-intent annotated Git tag baseline/rd6018-telegram-ui-fast-slot14-20261107, pushed to owned origin timspb/rd6018_bot. Node104 read-only verification at 09:43 UTC: rd6018-bot.service Active, PID231800, NRestarts0; D144 slot14 installed identity d49cb6d, transaction be4fce7576844e5c95df1ea8e6aeda15, D144_TRANSACTION_14.json present, prior image directories d144-backup-14, d144-old-14-app and d144-old-14-venv exist. No node104 writes or restarts in this sprint; physical controller and established Telegram UI baseline untouched.

Feature-only branch feature/main-mix-countdown-display. Narrow source change ONLY operator_hmi.py (HMI projection) and tests/test_operator_hmi.py; no change to panel_lifecycle, Telegram publisher, SignalAnalyzer, MAIN authority, safety, sample storage, firmware or hardware. Countdown uses accepted analyzer Imin epoch if available, otherwise valid analyzer seconds_since_current_min. A missing, NaN, Inf or negative analyzer clock no longer fabricates a fresh 3-hour countdown: HMI says Imin time unconfirmed. A new accepted minimum resets the displayed countdown through the existing analyzer timestamp; in-place 60-second Telegram refresh recomputes the caption from current time, no new timer. The destination label now respects actual intent: Recovery/Conditioning MAIN to MIX, Normal MAIN completion, AGM or unknown intent MAIN decision. Existing regulator/CV, readback and tail evidence requirements are unchanged. This is operator-facing information, not transition authorization or a guarantee that all independent safety gates have passed.

Regression evidence (Windows repository virtualenv, dummy offline TG_TOKEN): 122/122 targeted HMI, dashboard, panel lifecycle, graph refresh, signal analyzer, MAIN clock/authority tests PASS; 105/105 V3 UI suite PASS; Python compilation and git diff --check PASS. Additional HMI tests exercise missing clock, countdown advancing minute-by-minute without new analyzer sample, normal-vs-recovery destination, and invalid clock. Historical frozen source remains available; new change is NOT deployed, not merged to main. Future installation must use exact new-source SHA, safe retired-session Native+HA OFF proof and existing D145/D144 owner, without modifying or cleaning the slot14 backup before acceptance.

## Non-negotiable modularity and configuration canon (2026-11-07)

**No new monoliths.** This applies to all RD6018 changes, including operator HMI, charging algorithms, recovery, telemetry, logging, and release tooling. An existing oversized file is not a license to add another feature branch to it.

- One module owns each capability, state transition, clock, renderer, configuration value, and side effect. Separate read models, pure policy/formatting, orchestration, Telegram adapter, hardware execution, and persistence. Composition wires them; it must not reimplement their rules.
- Every user-tunable duration, threshold, limit, recipe parameter, choice, and policy belongs in the owning module's declared typed `variables.py` / `config.py` (or the canonical existing recipe/spec registry). Define units, default, range, provenance, override policy, and change effect. All consumers read that same definition; no scattered literals, shadow settings, duplicate copies, or hidden environment overrides.
- Presentational countdowns **derive** from the existing SignalAnalyzer/MAIN authority timestamps and configured hold duration. They never establish their own timer, storage, charge transition authority, or additional polling process. Different chemistry/intent must not be inferred from ad-hoc UI constants.
- Preserve exactly one Telegram panel lifecycle owner, one 60-second refresh task, and in-place edits. New UI features belong in focused read-model/presenter/component modules; the Telegram adapter stays transport-only. Do not expand `operator_hmi.py`, `runtime/production_runtime.py`, or `bot.py` with new cross-layer policy.
- Before each change: identify existing canonical owner and config source, perform the smallest source modification that implements the requirement, and remove superseded code rather than adding shims. Do not construct a parallel abstraction, extra proof/authorization, new service, duplicate observer, or alternative rollback path.
- Acceptance: focused module tests + existing architecture/UI regressions + actual entrypoint behavior where relevant. Record evidence and exact SHA in the runbook. Keep the deployed known-good baseline untouched until an explicit safe D145/D144 installation is authorized; never confuse source acceptance with live hardware/UI acceptance.
- If requested work needs a new setting or subsystem, extend the original semantic owner rather than opening an independent control plane. Reject any design that makes two modules authoritative for the same state.

## 2026-11-07 — MIX CV/CC accepted Delta presentation audit and fix, source-only

Scope: user ordered continued work on item 2 MIX indication, explicitly no node104 deployment during charging. Read-only static audit uncovered incorrect UI dependency: after a durable CV Delta accepted, a later live regulator CC caused operator_hmi.py to reject that accepted CV evidence and announce Delta unavailable; the converse CC->CV had same fault. The canonical finish evidence stores the accepted mode independently of current regulator; the controller/SignalAnalyzer retain sole decision authority.

Fixed presentation only: a new small pure read-only runtime/ui/components/mix_stage_progress.py owns the persisted MIX finish-hold label/countdown. It identifies confirmed Delta by durable finish_evidence.mode (CV -> delta I, CC -> delta V), delta_reported and valid accepted reference/delta, not by current live regulator. It displays the remaining hold from existing recipe-owned _effective_mix_finish_hold_seconds and persisted finish_hold_started_at, and labels missing evidence explicitly rather than inventing proof; invalid/future timestamps produce no fake countdown. Existing pre-confirmation live MIX CV Imin/Delta I and CC Vmax/Delta V paths remain in the same read model, with no new clock/publisher/observer/authority or physical call. operator_hmi.py delegates this one existing hold branch; panel_lifecycle.py untouched.

Regressions: 3 new operator HMI tests for accepted CV->CC/CC->CV mode changes and future hold timestamp; 48/48 HMI PASS, 134/134 targeted HMI/dashboard/panel/graph/SignalAnalyzer/MAIN/MIX PASS, 105/105 V3 UI PASS, Python py_compile and git diff --check PASS. Pure source only, still NOT deployed. Frozen known-good node104 D144 slot14 exact SHA d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b and backup must remain untouched until operator explicitly requests a safe deployment. Next sprint: journal event completeness and clear human wording, continuing on isolated source branch.

## 2026-11-07 — Human charge journal pass after MIX presentation fix (source-only)

Audited the existing journal chain: authoritative SignalAnalyzer accepted extrema produce MAIN_HOLD_START/MAIN_HOLD_RESET and MIX_IMIN_UPDATED/MIX_VMAX_UPDATED in runtime/charge/evidence/trace_context.py; existing production runtime log_event_sub writes them to the established charging_history.log, and the canonical journal component filters service CHECKPOINT/RESTORE rows before pagination (8 events/page). Durable V2_FINISH_HOLD_START is recorded by existing runtime/charge/runtime/mix_finish_hold.py; no second journal, telemetry collector, timer, or persistence path is needed. Full live event coverage of a charge cycle remains unproven without a new cycle; do not fabricate past events or equate source audit with physical acceptance.

Found human-factors issue: MAIN_HOLD_START was rendered as if the entire transition hold had definitively started, but the source event only proves the analyzer accepted an Imin epoch (tail readiness and decision gates are independent). Narrow two-string presentation change in runtime/ui/components/journal.py now reads 'Imin принят; отсчёт от минимума' and 'Новый Imin; отсчёт от минимума заново'. Updated existing journal milestone assertions in tests/test_operator_journal_milestones.py. No state transition, safety, output, journal data format, or event producer changes. Tests 116/116 combined operator journal/HMI/dashboard/panel PASS and 105/105 V3 UI PASS, compilation and git diff --check PASS. No node104 deployment per operator instruction; frozen known-good D144 slot14 d49cb6d remains untouched. Next work: continue journal source-to-persisted-event mapping and catalog program parity on HOME-PC, keeping every value at its canonical modular owner.

## 2026-11-07 — 12 native charge recipe variants: ownership catalog audit (source-only)

Audited the canonical native recipe catalog: exactly 3 chemistries Ca/Ca, EFB, AGM x 4 intents normal, recovery, conditioning, diagnostic = 12 descriptive variants, NOT 12 independent controllers. PREP/MAIN/DESULFATION/Recovery SAFE_WAIT/MIX/Final SAFE_WAIT/COOLING/DONE are existing stage-specific production authorities. The diagnostic variants exclude automatic high-voltage DESULFATION, MIX and associated SAFE_WAIT from their advertised stage paths. Native recipe parameters come from strategy-owned VariableSpec declarations; AGM generic MAIN voltage is not editable; MAIN C-rate copies cap at 0.1C; pinned session settings validated through existing native selection and guarded START rather than separate runner. Actual physical stage traversal remains conditional on live evidence and safety, not guaranteed by catalog metadata.

Confirmed catalog ownership mistake: STAGE_OWNERS labelled FINAL_SAFE_WAIT as runtime.charge.runtime.mix_scaffold although existing production stage_authority.apply_authoritative_stage_tick delegates final SAFE_WAIT to runtime.charge.runtime.final_safe_wait_authority.apply_final_safe_wait_authority. Fixed ONLY metadata declaration in native_recipe_catalog.py to the actual existing owner; regression in test_native_recipe_catalog.py checks catalog owner vs production dispatch and exposure for 9 non-diagnostic variants, exclusion for 3 diagnostic variants. No physical runtime code, charge strategy, settings, panel lifecycle, service or hardware modified.

Acceptance: 7/7 focused catalog/default-execution tests PASS; extended native-policy, real-stage, pinned-selection/start, persistence/restore and safe-wait/MIX/desulfation suites 29/29 PASS with PYTHONPATH including repository tests directory. An initial expanded invocation without tests on PYTHONPATH failed module import test_start_transaction_service; rerun with correct test PYTHONPATH passed, no code workaround. Full 12-variant physical battery charge cycles are NOT verified by these tests. Continue separate static parity inventory and preserve node104 D144 slot14 d49cb6d until operator permits deployment.

## 2026-11-07 - Canon: externalize literal configuration and decompose touched monoliths
All meaningful hard-coded numeric and semantic values must belong to one typed config/spec owner; human-facing UI strings reside in focused UI label catalogs. Protocol constants and trivial math are documented exceptions, not arbitrary tunables. Any monolith touched for a feature is incrementally decomposed at the affected boundary, with behavior preserved and redundant logic removed. No new control plane, timer, or duplicate owner. This is a source policy change only; slot14 d49cb6d/node104 remain untouched.

## 2026-11-08 - Active autonomy and chat migration pointer
Current source-only continuation plan: docs/assistant/RD6018_AUTONOMOUS_HANDOFF_2026-11-08.md. Ready-to-paste new chat instruction: docs/assistant/RD6018_NEW_CHAT_PROMPT_2026-11-08.md. Follow AGENTS.md and latest assistant checkpoint; complete source stages in priority order, test and push only to owned feature branch. Next: callback and PanelLast single-publisher acceptance, then snapshot parity, MIX/MAIN display edges and broader offline regression. Production node104 D144 slot14 d49cb6d remains untouched until owner separately authorizes physical deployment with direct ESP evidence. Autonomous wake scheduling belongs to the receiving chat, not this repo or a second agent.

## 2026-11-08 — P3 MIX finish countdown rejects invalid current-clock input (source only)

`runtime/ui/components/mix_stage_progress.py` formats the already persisted MIX Delta finish-hold; it does not own the timer or transition. A valid `finish_hold_started_at` and duration with `now_s=NaN/Inf` previously caused `math.ceil()` to raise, and `hmi_auto_stage_progress` could blank the operator status due to its broad presentation exception handler. The pure presenter now validates `now_s` using its existing `_finite` parser and displays `Финишная выдержка · время не подтверждено` for NaN/Inf/negative/zero, without inventing a countdown. Accepted CV/CC Delta semantics and `SAFE_WAIT` destination remain unchanged for valid clocks.

Windows HOME-PC offline focused HMI/MIX/button suite **64 passed, 19 subtests passed**. Source-only code and tests; production node104 remains frozen at D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`, no deploy, restart or physical action. Further P3 audit may inspect future accepted-evidence timestamps and LIVE owner visuals, but software tests do not establish live charge acceptance.

## 2026-11-08 — P4 offline matrix: recipes, MAIN guard, restore, Telegram (no physical tests)

HOME-PC Windows venv selected 6-suite cohort: native recipe catalog (3 chemistries × 4 intents), native restore parity, guarded restore hold, MAIN admission, cold-start recovery and terminal Telegram panel. Unfiltered result **50 PASS / 1 FAIL / 114 subtests PASS**. Single failure is `test_main_guard_admission.py::test_missing_file_corrupt_file_and_symlink_do_not_create_identity` at Windows `Path.symlink_to()` before policy assertion (`WinError 1314`, insufficient symlink privilege). A scoped rerun excluding ONLY this platform-dependent case is **50 PASS / 1 deselected / 114 subtests PASS**. WSL Ubuntu 24.04 Python 3.12 separately runs the full MAIN guard admission test module, including real symlink verification: **10 PASS / 20 subtests PASS**. No weakening/deleting safety tests or fake success claim.

Attempted broader WSL six-suite cohort with system Python 3.12; test collection blocked by missing `python-dotenv` and `aiogram`. No system package installation or virtualenv mutation was performed; full Linux matrix is NOT accepted. These are offline behavior regressions only, NOT 12 physical battery cycles, runtime recovery acceptance, or ESP Native output proof. Production node104 frozen D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b` remains untouched. Recommended subsequent work: verify an existing isolated Linux test venv before broad P4, and continue source-only P3/P4 checks; never perform node deployment without separate authorization.

## 2026-11-08 — P4 transaction contract regression (source-only)

WSL Ubuntu 24.04 Python 3.12 D144 state-preserving/owner binding suite: **25 passed + 7 subtests**. HOME-PC Windows recovery guard, recovery service, recovery resume Output transaction, link-session policy: **31 passed + 14 subtests** after running from repository root. The isolated old recovery test fixture incorrectly treated optional `HassClient.verify_live_programming(ovp_v, ocp_a)` values as mandatory and demanded an OCP write on the existing guarded Iset-only desulfation MAIN return. The fixture now models optional verification fields, preexisting adequate OCP, and requires the same durable guard/source transition without redundant OVP/OCP setters. Only test code was changed; the existing ExecutionPort, source owner, protective limits and physical command paths remain untouched. This is not production deployment or hardware acceptance. More detailed checkpoint: `docs/assistant/RD6018_CURRENT_CHECKPOINT.md`.

## 2026-11-08 — P3/P4 MIX UI proof and orphan retirement read-only guard

The existing `mix_finish_hold_status` formats read-only persisted Delta evidence. A snapshot containing `delta_reported=True` and `finish_evidence.available=True` but nonpositive accepted Delta/reference previously advertised a confirmed ΔI/ΔV. The pure presenter now requires positive finite reference and Delta before displaying confirmation, without changing SignalAnalyzer or charge transitions. `application/controller_session_retirement.py` orphan-binding read path now declines partial controller adapters lacking canonical `STAGE_MAIN`, `STAGE_MIX`, `STAGE_IDLE` rather than throwing and disrupting the Telegram keyboard. No new safety owner, timer or Output command. Specific regressions cover CV/CC invalid proof and the partial controller alongside the valid orphan-MIX path. Home-PC offline focused **24 passed + 21 subtests**, expanded UI/operator/managed safety/orphan **314 passed + 39 subtests**. No physical acceptance; node104 remains frozen at D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`.

## 2026-11-08 — P5 current feature source manifest (no staging)

Canonical offline `tools/node104_atomic_deploy.py manifest` on clean HEAD `bf9e44960d19b4e505b32d9f63146781cfdfe67b` reports **1411 tracked source files** and `archive_sha256=8cf72a343b90ea9575b422cbc72a9adcb033b42dc4978000e1e01e02db3c5fe7` for `node104/rd6018-bot`. WSL source-release/atomic-deploy tests: **19 PASS + 9 subtests PASS**. The command only generated a read-only source manifest; no staged artifact, deployed build, backup or physical evidence. Compare current source hash to the historical D123 Sprint 61/62 manifest records only as separate revisions. Actual installed revision, durable rollback preimage, fresh ESP Native state and bench/physical acceptance remain separate, unproven boundaries; node104 production remains frozen D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`.

## 2026-11-08 — P5 MAIN display invalid recipe duration

`hmi_auto_stage_progress.py` now reads `MAIN_POLICY.tail_hold_hours` through the existing finite-value parser. Previously None/string values could make a presentation-only exception erase accepted `Imin` status; NaN/Infinity were shown as ordinary wait-for-CV. Pure `main_stage_progress.py` now displays `время выдержки не подтверждено` for invalid hold duration when tail evidence is otherwise ready, without fabricating elapsed time or a MAIN → MIX countdown. The existing charge controller, recipe authority, accepted analyzer clock, safety and physical effects were not changed. Red test reproduced four failure cases; after the source-only change the focused Windows HMI tests **82 PASS / 25 subtests PASS**, expanded UI/operator/safety/orphan **315 PASS / 43 subtests PASS**. Node104 remains frozen D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`; no physical or live acceptance.

## 2026-11-08 — P5 read-only Native callback coherency after MIX V2 alerts

`ESPHomeTransport` receives independent SensorState battery-voltage and authoritative Vset callbacks; the canonical age metadata is per-channel and must not be reset by a cache read or an unrelated callback. Source-only regression in `tests/test_esp_home_transport.py` simulates both readings degraded, Vset-only recovery, then battery callback recovery without a Native disconnect. This possible pattern explains why two different guard warnings can occur in successive samples, but DOES NOT establish actual incident causation. In the existing 500-line transport, the two duplicated reconnect-completeness conditions were consolidated into one **pure** helper `runtime/physical/transports/esp128_callback_coherence.py`, shared by the 8-second reconnect wait and the outage-epoch clearing decision. No new controller, telemetry timer, guard, physical route or policy. Source-only WSL isolated venv transport/safety/metadata cohort **63 PASS**. Windows broad cohort had one D106 Linux-only `fcntl` collection failure, and isolated Linux transport suite passed in full. Actual node104 callback/link/Output history is unknown; no device/HA/ESP access or physical writes, deploy, restart, threshold change or acceptance. See `docs/assistant/RD6018_V2_TELEMETRY_INCIDENT_2026-11-08.md` for details.

## 2026-11-08 — Exact-byte D061 historical trust anchors on Windows checkout

When HOME-PC has `core.autocrlf=true` and the repository uses `* text=auto`, the seven exact-byte D061 acceptance assets under `tools/acceptance_guard/` can be checked out as CRLF even though their canonical Git blobs retain the original LF and match pinned SHA-256. This causes fail-closed historical D061 stage-pairing/takeover tests to reject the worktree. Keep `.gitattributes` `-text` for `source-manifest.json`, `__init__.py`, `guard.py`, `adapters.py`, `transient.py`, `pairing.py` and `takeover.py`; restore only exact committed Git bytes, never update pinned hashes, weaken digest checking, or regenerate reviewed overlay. D061 Linux isolated-venv tests after scoped checkout fix: **50 passed**. The broader Linux discovery was **interrupted** at 14% (437 passed, 2 skipped, 1 failed, 5 errors), so it is not full acceptance. Separate targeted source-only WSL suites were **102 passed** and **88 passed**. Production node104 remains frozen at D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`; no deployment or device work. Handoff and checkpoint capture precise steps and remaining evidence needs.

## 2026-11-08 — D123 historical ownership/OVP test parity (source-only)

In the isolated WSL full-suite triage, the collected test-ID slice 400–520 initially had 3 failures. The trace single-writer check counted a legitimate separate Git worktree at `.worktrees/dryrun_virtual`, so the test now scans tracked `*.py` paths from the current checkout rather than blindly traversing nested worktrees. AGM step and MAIN→DESULFATION effect tests expected `set_ovp` and `set_ocp` at every stage transition; the current canonical `charge_controller._add_phase_limits/_add_desulf_limits` deliberately programs stage Vset/Iset only and leaves hardware protection registers in place. The tests now explicitly assert no redundant OVP/OCP action while preserving stage and current-limit assertions. No runtime behavior or safety mechanism changed. Focused affected D123 suite: **17 PASS**. Full ordered slice of 121 collected IDs: **121 PASS** (WSL isolated Python 3.12). This is not an exhaustive 3033-test suite pass; previous full suite remains interrupted. Production node104 stays frozen D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`.

## 2026-11-08 — Historical D123 Sprint57 pre-ON OCP fixture parity

The existing MAIN Guard pre-ON strategy checks fresh Native Output OFF, protection status and Iset against the durable current ceiling; it is not the owner of OVP/OCP programming and cannot authorize Output ON. The old Sprint57 test expected an OCP mismatch to block this narrow reconciliation. Test-only correction splits the cases: protection trip and Iset mismatch still block; OCP variation does not add an artificial pre-ON gate, and a fresh `RECONCILED` assessment still cannot call verified Output ON. WSL bounded collected test IDs 521–700: **181 PASS** after correction; no runtime or physical modifications. Whole 3033-test suite has not completed.

## 2026-11-08 — P5 SQLite worker shutdown leak in source-only pytest

A full-suite segment previously completed all 200 assertions but could not exit; Python `threading._shutdown` waited for `aiosqlite._connection_worker_thread`. Isolated two tests opening the process-global battery-registry DB without owning its shutdown: Manual interrupted restart and MIX diagnosed-cell-fault veto. Both tests now mock the unrelated read-only battery-registry/history lookup, preserving real manual state and diagnostic-veto logic, physical safety fakes and no-Output contracts. In `test_manual_context.py`, source scan is now restricted to Git-tracked files of the current checkout instead of descending into independent nested worktrees/virtualenvs. Linux isolated venv combined tests: **13 PASS exit 0**; bounded source-test slice 1101–1300: **200 PASS exit 0**. No production runtime or DB ownership changes. Full 3033-test suite remains unverified; continue bounded chunks and track exit codes (a pytest summary alone is insufficient).

## 2026-11-08 — Canon clarification: routine OVP/OCP programming was removed

Correction to shorthand in earlier P4/P5 notes: automatic charge transitions do **not** retain or recompute old positive OVP/OCP thresholds as routine stage protections. Normal START, MAIN, DESULFATION and stage transitions program Vset/Iset only. The pre-Output-ON boundary retires stale nonzero OVP/OCP values to zero with authoritative readback when no explicit recipe-owned protection is requested; zero denotes disabled physical OVP/OCP threshold. Explicitly requested protection (e.g. MIX OCP) remains transaction-specific. Hardware protection-trip status, voltage/current/temperature ceilings, fail-closed readback and 900 s lease remain active. This wording supersedes earlier descriptions such as 'pre-existing adequate OCP retained' or 'physical protection registers left in place' for normal stages. No change to production runtime, thresholds or node104 is authorized by this clarification.

## 2026-11-08 — P5 tracked production inventories and recipe first SET

Bounded WSL collected test IDs 1701–1900 initially 199 PASS/1 FAIL: Output-enable inventory walked a separate nested `.worktrees/dryrun_virtual` and falsely counted nine actuator paths. `tests/test_output_enable_inventory.py` now enumerates Git-tracked production `.py` in THIS checkout without modifying its frozen call-site list. Rerun **200 PASS, exit 0**. IDs 1901–2100 initially timed out at 56 PASS because production-module namespace tests recursively scanned nested worktrees/virtualenvs; their retired-module checks also saw only `__pycache__` directories for `runtime/application` and `runtime/charge/shadow`. `tests/test_production_module_namespace.py` now checks tracked production files and tracked retired paths, preserving exact forbidden symbols and modules. Rerun **200 PASS, exit 0**. IDs 2101–2300 initially 198 PASS/2 FAIL: first recipe SET test expected old OVP/OCP programming; recipe-policy graph test scanned nested worktree. Changed test expectation to Vset/Iset with omitted OVP/OCP (None), and scanned tracked production Python only. Rerun **200 PASS, exit 0**. These are test-scope and fixture fixes only, no physical command code edits.

Owner correction: routine OVP/OCP setting was **removed** on normal START and MAIN/DESULFATION/stage transitions, not merely skipped on some repetitions. Existing pre-ON boundary clears old positive OVP/OCP to zero when no explicit recipe-owned protection is requested, verifying readback; explicit MIX OCP is transaction-specific. Never describe old OVP/OCP thresholds as retained ordinary stage protection. Hardware trip status, chemistry/absolute V/I bounds, temperature, Output readback and 900s lease remain separate safeguards. Source safety/charge production unchanged. Next continue bounded IDs 2301–3033; full suite remains unaccepted until coverage + exit status established. No node104 interaction.

## 2026-11-08 — обновлён автономный план P1–P5 и закрыт блок 2301–2500

После опубликованного `99dacdd156cd549b7264be086b486db01400c010` проверены clean branch `feature/main-mix-countdown-display`, origin `https://github.com/timspb/rd6018_bot.git`, ahead/behind 0/0; активных RD6018 Codex/Python процессов не обнаружено. Составлен самостоятельный актуальный план `docs/assistant/RD6018_AUTONOMOUS_PLAN_2026-11-08.md`: P1–P4 исходные границы закрыты, P5 приоритет — полный WSL suite с контролируемым exit status, затем инцидент Native V2 и отдельно release-evidence. Разрешены только исходники, документация, офлайн-тесты. Физический node104 по-прежнему frozen D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`.

Собранный исторический набор содержит 3033 test IDs; до нового этапа проверенные куски 400–2300 завершились успешно (один skip). Исследован 2301–2500: первоначально 199 PASS, 1 FAIL из-за `test_transition_audit_retirement.py` обхода вложенного `.worktrees/dryrun_virtual`, и зависание в shutdown после успешных проверок. После минимального изменения тестового сканирования через `git ls-files -z '*.py'` legacy-retirement модуль 3 PASS. Изоляция 2301–2400 дала 100 PASS / exit 0; 2401–2500 — 100 PASS, но timeout 124. Виновный отдельный `tests/test_telegram_start_dispatch.py`: 4 PASS при зависшем общем aiosqlite worker; соседние start-transaction и terminal panel тесты завершались штатно. Добавлен только `asyncTearDown` закрывающий process-global test `database.close_db()` после каждого изолированного dispatcher теста; `test_telegram_start_dispatch.py` теперь 4 PASS / exit 0. Итоговый повтор 2401–2500 — 100 PASS / exit 0, затем всего 2301–2500 — **200 PASS / exit 0 (20.26s)**. Два прежних DeprecationWarning `utcfromtimestamp` не менялись. Тестовый диагностический файл `_sqlite_trace_tmp.py` должен быть удалён до коммита; он не часть проекта. Runtime/physical/DB implementation не изменён. Следующие тесты: диапазоны 2501–3033 и непроверенные 1–399 с точными exit codes, только затем контролируемый полный suite. Офлайн результаты не подтверждают live Telegram, производство и физическую приёмку.

## 2026-11-08 — P5 partitioned regression and single Telegram renderer

Original 3033-ID source list now has bounded exit-0 coverage. Final portions: **2701–2900 200 PASS**, **2901–3033 133 PASS**, **1–200 198 PASS + 2 skipped**, **201–399 199 PASS**. Earlier 400–2700 cohorts appear in checkpoint. Partitioned completion is not an uninterrupted whole-suite acceptance; monitored continuous run remains.

Corrected actual UI boundary violation: HMI components no longer instantiate aiogram buttons, but pass callback-row descriptors to the existing Telegram renderer. No new publisher, action selector, timer or physical route. Architecture inventories now scan current Git-tracked sources, not a separate worktree; exact approved physical-call inventory retained. Offline ESP connector/smoke fixtures use loopback addresses strictly for test configuration validation. PREP→MAIN no longer expects removed OVP/OCP commands. Focused UI/HMI/V3 regressions 60 PASS. node104 frozen.

## 2026-11-08 — P5 full-suite order dependency and HMI instance isolation

First continuous WSL full suite: **3030 PASS, 3 skipped, 1 FAIL, 6 warnings, 427.83 s**. The sole manual-interrupted callback failure was introduced at collection-time by globally stacked HMI wrappers: `rd_ownership_recovery` prepended `rd_ownership_hands_off` using its captured manager on another app. Existing wrapper is now app-bound: it never augments markup for `app_arg is not app`. Same-app behavior and all safety decisions preserved. New regression for own/foreign apps; focused 17 PASS, full collection with only former failed test selected 1 PASS. Re-run whole suite for genuine acceptance, node104 remains frozen.

## 2026-11-08 — P5 continuous full-suite PASS at d13d2cf

Actual owned feature HEAD `d13d2cfcce4401728e37d5481167aa5516fc363f` at test start, own remote `https://github.com/timspb/rd6018_bot.git`. Monitored uninterrupted WSL Ubuntu 24.04 isolated Python 3.12 `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests` completed **EXIT 0: 3032 passed, 3 skipped, 6 warnings in 431.06s (7m11s)**. Earlier uninterrupted run at `4a5f7f6` was 3030 passed, 3 skipped, 1 failed and showed cross-app HMI wrapper ownership leak, fixed in `d13d2cf`, now proved resolved end-to-end. Warnings: 5 `datetime.utcfromtimestamp` deprecations `database.py:238` and 1 empty legend warning `graphing.py:203`, nonblocking, follow-up source-only cleanup. This PASS is entirely offline: no physical IO, no claim of live Telegram or node104 acceptance. Production remains D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`, unchanged. Next: update plan/checkpoint/runbook, commit/push documentation; inspect one focused responsibility of oversized `runtime/production_runtime.py` (3635 lines) and incrementally extract only if a clear cohesive owner boundary exists, with new regression and full/targeted test evidence. Do not reimplement owner, or expand physical/safety surface. Freeze source-manifest only for exact final HEAD, offline, without deployment.

## 2026-11-08 — Incremental monolith decomposition: pure stage duration presentation

After verified continuous full-suite 3032 PASS / 3 skipped / exit 0 at `d13d2cf`, documentation baseline was recorded in owned branch commit `9a7a436`. For the next source-only stage, inspected `runtime/production_runtime.py` (3635 lines) and selected only its cohesive **pure UI duration formatting** responsibility; no charge-stage or hardware control moved. Relocated `_format_eta_compact` and `_format_seconds_compact` unchanged in semantics into new focused `runtime/ui/components/stage_duration.py` as `format_eta_compact` / `format_seconds_compact`, removed the old monolith implementations, and imported functions under their existing private runtime names. Added `tests/test_stage_duration_presentation.py` with invalid/blank/zero/hours/minutes/string input equivalence assertions. Existing stage progress, timer authority, counters, callback and publication paths unchanged. Focused WSL tests: `test_stage_duration_presentation.py`, `test_hmi_auto_stage_progress.py`, `test_operator_hmi.py`, `test_operator_button_rules.py`, `test_operator_dashboard.py` **82 PASS in 26.20s**. This is source-only decomposition and **not** a new continuous full-suite PASS after the change; previous full-suite pass was before extraction. No node104 or physical actions. Next: diff/compile, commit/push scoped module/runtime/tests/docs; inspect further monolith responsibility only with demonstrated single-owner extraction and regression, not mechanical splitting.

## 2026-11-08 — P5 full regression after stage-duration extraction

On tested source HEAD c32a37d19a5815a3e03c6ab503b03fba580acb38, the uninterrupted WSL isolated pytest -q tests completed: **3034 passed, 3 skipped, 6 warnings, exit 0 in 378.68s**. The extraction to runtime/ui/components/stage_duration.py also passed 115 focused HMI/Telegram/architecture tests. Five warnings are database.py:238 utcfromtimestamp deprecations; one is graphing.py:203 empty legend. This source-only result does not prove physical node104, real Native V2 callback events or live Telegram acceptance. Production remains frozen at D144 slot14 d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b; no node access, restart, deployment, output or physical command. Do not decompose further for file size alone; remaining work requires a concrete defect or separate live approval.

## 2026-11-08 — Operator-approved 300s managed telemetry recovery (source-only)

Ordinary polling and MAIN/MIX stage-change callback delays share one bounded 300-second recovery window owned by the existing ManagedRuntimeSafetyGuard. This is a wait for fresh data, not accepting stale data as fresh. The strict 20s preflight/readback validation remains unchanged; isolated runtime callbacks with fresh Output/protection evidence can recover without immediate software STOP. Actual Native disconnect retains its epoch; a standalone callback fault starts at first detection. Missing metadata, unknown Output, stale protection, dangerous measured values and known hardware trips remain fail-closed. A pure runtime/safety/telemetry_recovery.py classifies eligibility. The guard returns a recovery-pending flag on a copied sample; data_logger defers controller ticks; existing legacy and soft watchdogs do not issue a competing early OFF within the same guard-owned window. At 300s, fail-closed still applies. The edge safety lease remains 900s. Source-only targeted regression: 190 PASS, with 54 supplemental focused PASS (overlapping suites); full-suite on new HEAD is pending. No node104 writes, deployment, physical test or live acceptance.

## 2026-11-08 — 300s software communication watchdog also above 15V

Owner decision: remove the accelerated 60-second communication-loss timeout at U > 15 V. `WATCHDOG_TIMEOUT_S` stays 300s; historical `HIGH_V_FAST_TIMEOUT_S` remains a compatibility symbol but its default is now 300s. Deleted the duplicate `WATCHDOG_HIGH_V` software shutdown branch in `runtime/production_runtime.watchdog_loop`; the remaining watchdog uses one 300s timeout regardless of voltage. Existing confirmed physical trip, unsafe voltage/current/temperature checks and 900s edge safety lease remain separate and immediately enforceable. This does not authorize operation on dangerously out-of-range telemetry. Regression `test_v3_charge_logic_dependency_contraction` checks 300s equality and absence of early-off path. Focused safety/watchdog tests 76 PASS. Source-only; production node104 not changed.

## 2026-11-08 — High-voltage 300s watchdog final full-suite acceptance

Owner-requested removal of the 60s software communication-loss timeout when U > 15V has now completed a monitored full WSL isolated test run at source baseline `85477d1e8e3512cf052dc3529c65c49a8b54a255` plus the scoped source diff: `pytest -q tests` **3048 passed, 3 skipped, 6 warnings, EXIT 0 in 410.81 seconds**. The normal watchdog remains 300s. `HIGH_V_FAST_TIMEOUT_S` is retained for historic compatibility/diagnostics with a new 300s default; `WATCHDOG_HIGH_V` branch is absent from `runtime/production_runtime.watchdog_loop`. Architecture test explicitly asserts no accelerated high-voltage timeout and a single software stop callsite. Physical safety, OVP/OCP/OPP protection, unsafe voltage/current/temperature handling and 900s safety lease have not been changed. This is source-only acceptance, NOT an installed or physically tested node104 release. The six warnings (five datetime deprecations and one empty Matplotlib legend) remain nonblocking. Do not continue mechanical monolith decomposition without an actual responsibility boundary or regression. Commit and push only the seven scoped files to the verified owned feature branch; confirm clean status and upstream 0/0. Production remains D144 slot14 `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b`.

## 2026-11-08 — Node104 read-only deployment preflight: PARTIAL / HOLD

Owner approved preflight, not unconditional live deployment. Source HEAD `aaa17c744464dce44cf5839c6a81e784a21430e9` clean/synced. Canonical offline manifest returned archive SHA256 `3e138f751d09b9008737f363517cf8a72b78bf9cdd28f62c9d3507b2c69261b9`; no staging or deployment. Via existing HOME-PC node104 profile, read-only inspection observed `rd6018-bot.service` active/running, PID 231800, ActiveEnterTimestamp 2026-11-07 08:41:27 UTC; filesystem 7.7 GiB with 3.5 GiB available (54% used). Existing app/venv and pinned D148 collector paths were present. Actual installed source SHA was not verified. Attempted direct read-only D091/D148 ESP Native physical collector execution was blocked by an execution safety system. Therefore actual live R18 Output, U/I, lease, session state, ESP identity, HA comparison and D091 OFF proof are UNKNOWN. Release HOLD: NOT PHYSICALLY ADMITTED. No node104 write, stage, deploy, service restart, Output, lease, setpoint, database or ESP modification. Do not attempt alternate-wrapper bypass of execution-policy denial. Historical D144 slot14 source `d49cb6d1bb24fa3d2496ca4564aaf1d4ea91fa5b` is not newly observed live installed evidence.

## 2026-11-08 — AUTO/MIX STOP fail-closed recovery fix (SOURCE ONLY)

Operator screenshots showed AUTO/MIX paused, repeated V2 protection `battery voltage is implausible: 0.010V` while a separate screen showed battery around 12.87–12.88V, and `/recovery_clear` returned **no active recovery quarantine**. These samples are at different times; neither proves which ESP Modbus/Native report generated 0.010V. Owner reports physical Output OFF and that ordinary STOP cannot retire the AUTO session. The real code boundary: `runtime/production_runtime.py::_hard_stop_charge()` calls the existing `ExecutionPort.request_verified_off()` and raises `RuntimeError("STOP refused: physical Output OFF not verified")` if the OFF receipt is false; `operator_managed_stop.py::_stop_exact_session()` only ran its software-retirement fallback after `OutputOffNotConfirmed`, so this ordinary refusal path left AUTO active. The old fallback also retired on a single untyped `switch=off, current≈0` read without checking Native provenance or age.

Source-only repair to the **existing** managed STOP owner (no second orchestrator, no new command or safety timer): allow the fallback for either `OutputOffNotConfirmed` or that **exact** RuntimeError, never for other runtime failures. Before retiring the **same identity-locked** AUTO session, require a new independent read with typed ESP Native SensorState for both canonical Output R18 (`output_state_code_v2=0`) and current (`abs(I)<=0.05A`), metadata `source=esp_native_api`, `native_type=SensorState`, `status=ok`, monotonic timestamps **strictly after** the specific STOP attempt began, valid finite age **<=8s**, and accepted canonical freshness for both. No HA-only/cached/unknown/NaN/nonzero current/stale callbacks, no changed session identity. Fault containment stays latched; no ON, setpoint, lease or hardware safety policy modification, no modification of strict pre-ON proof. Focused STOP + recovery + safety cohort **51 PASS**. Full test suite pending in `/tmp/rd6018_stop_native_fallback_full_20261108.log`. **NOT DEPLOYED**; installed node104 remains older D144 slot14 until new tested candidate passes and production admission is explicitly established. If Native genuinely has no fresh callbacks, STOP continues to fail closed; actual node104 failure still requires Native evidence and service logs to establish.

## 2026-11-08 — Safety decomposition: source-only release candidate

Protection and Output decomposition complete in source commit `5ed03cc49a6a58ca0aae26e6aa5fbb0ebcb77c5f`: one safety watchdog task, standalone managed guard + strict guard + runtime guard in `runtime/safety/`, separate critical telemetry/electrical envelope/foreign Output/edge lease/temp integrity policies, pure `output_policy.py` and existing verified Output transaction in `application/safe_output_coordinator.py`. No duplicate actuator or second watchdog. Historical D061 pinned overlays retained byte-identically. Full checkout WSL suite 3065 PASS / 3 SKIP / 0 FAIL; exact source-only archive 3058 PASS / 10 SKIP / 0 FAIL. `source.tar` SHA256 `973e69bf8d4d4fb9df5b2fd87a2faa493b7986b72a5fe7ff1981676b4a63d706`, manifest SHA256 `745bf13eecf0d851fe3c6bf70013e207de2489814bb59b1978a7fa6c16760df3`; full stage path and validation log in assistant checkpoint. **SOURCE ONLY.** Standard D145/D090 deployment remains blocked pending current node104 preimage + live independent typed Native/HA Output OFF evidence and fresh D146 profile. Direct WSL SSH root@192.168.1.104 on 2026-11-08 returned permission denied; no production actuation or service restart. Do not reuse old profile pins. Preserve unresolved 0.010V and stalled MIX evidence until exact incident provenance is determined.

## 2026-11-09 — D137 restored history and D145 access-mode correction (source-only)

D137 now selects the newest valid paired `COMMITTED` D144 transaction rather than the numerically newest transaction of any phase. `RESTORED`/`FAILED`/`PREPARED` remain immutable history and do not supersede an installed release. Every COMMITTED identity must pair with its transaction and installed app/venv inventory; malformed or ambiguous records fail closed. D145's previous staging root was intentionally mode 0700, and its later candidate parent was also mode 0700; copying the tree retained inaccessible app/venv permissions. The canonical owner now prepares only candidate app/venv as root:`rd6018`, applies minimal group read/traversal and executable group bits, verifies every entry and content identity before D144 can stop the service. Candidate parent/backups remain private; systemd restrictions are unchanged. Focused cohorts: D137/D138/D144/D145 + D090/profile/archive **103 PASS** before final refinement; final owner/D137/entrypoint **37 PASS** after refinement. See current assistant checkpoint for exact changed files, rerun requirement and operational state. **Production installation remains HOLD** because fresh Native/HA/D137 evidence was inaccessible from the current SSH sandbox; old stage/profile pins are stale and must be rebuilt.


## 2026-11-09 — Recipe Studio RS-0: approved scope and baseline

Owner approved development of a usable **PC UI and Telegram recipe editor**. Canonical implementation plan: `docs/assistant/RD6018_RECIPE_STUDIO_PLAN_2026-11-09.md`. Priorities: P0 physical/manual control first; Recipe Studio RS-0→RS-4 source-only work may proceed in small verified steps. Build atop existing native-draft library, user step-recipe library, single START owner and existing Telegram handlers. No second charge engine, daemon, ACL, data store or parallel panel lifecycle.

RS-0 confirmed code owners and a concrete mismatch: `tools/recipe_visual_editor_prototype.html` exports `rd6018.recipe_visual_draft.v1`, **not** executable `recipe_schema` or `NativeRecipeDraft`. It includes `kind=native` stages and `repeat_count`, neither executable by the step runner. Must not treat the visual JSON as ready-to-run. Native drafts are schema-checked and execution-subset checked separately; existing `require_supported_native_execution` rejects unsupported overrides. Target architecture: one visual UI with explicit native-vs-step editing modes; one canonical library for PC and Telegram; backend validation; immutable revision and session digest.

RS-0 regression on owner/recipe contracts: **26 PASS, exit 0** in WSL Ubuntu 24.04, `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q` across ten recipe/native/catalog/UI test files. No runtime edit, deploy, restart, Output/setpoint/ESP command. Production node104 remains D144 slot16 COMMITTED source `3f50133` and is independent of these source edits. Next scoped work: RS-1A pure offline canonical export/import for the *supported* step recipe subset with explicit rejection of unsupported native stages, tests before any backend/Telegram wiring.


## 2026-11-09 — Recipe Studio RS-1A offline canonical bridge

Implemented **source-only** extension of existing `tools/recipe_visual_editor_prototype.html`: a separate `Экспорт SET/OFF/WAIT` produces exactly canonical `{id,version,steps:[{action,params,until}]}`; the existing import recognizes that canonical format and converts it back to visual `CUSTOM` stages. Draft JSON remains a separate, explicitly non-executable format. UI now exposes recipe ID (ASCII), version and local preliminary U/I ceilings; the latter are **not** hardware-authoritative and do not grant START or replace server `RecipeLibrary/recipe_schema/recipe_preflight`.

Fail-closed conversion refuses visual `kind=native` and named dynamic `MAIN/MIX/...` stages, unsupported repeat_count, non-zero minute budgets not expressible in the canonical format, mismatched Output action and U/I, stale/invalid predicates, unsigned/zero time waits, invalid step count/identity, SET exceeding local provisional ceilings, and WAIT not immediately preceded by OFF. Canonical import validates structure, fields, ceilings, OFF/WAIT sequencing and unknown actions before visual transformation. The bridge **does not** translate chemistry/capacity visual metadata into executable behavior; no actuator paths are added.

Added `tests/test_recipe_visual_canonical_bridge.py` with Node.js execution of the actual functions extracted from HTML; checks real Python `parse_recipe + inspect_recipe` for round-trip and rejection cases. Final focused run including user-recipe, native-draft, START-selection and UI catalogue tests: **34 PASS, exit 0**, WSL Ubuntu 24.04. Extracted embedded JavaScript `node --check` PASS; `git diff --check` PASS. No node104 deployment/restart, ESP/HA access, Output/charging/lease action, new backend, extra recipe runner or Telegram modification.

**Next:** RS-1B — replace provisional browser-only validation/import behavior with an explicit offline contract-based check and save flow through the **existing** `RecipeLibrary` / native draft library; expose immutable version, actual `VariableSpec`/supported-execution limits, and compare browser preview with backend admission. Do not expose a new unauthenticated network listener. Physical/manual control P0 remains the higher operational priority and must be accepted separately.

## 2026-11-09 — Recipe Studio RS-1B: canonical offline check/save (source-only)

Implemented offline bridge to existing **production canonical owners**, without a new daemon, API, device port, authorization layer or store:
- `runtime/charge/programs/recipe_studio_import.py`: `inspect_step_document` and `publish_step_document` accept **only** `{id, version, steps}`, apply existing `parse_recipe` with actual production limits and `inspect_recipe`, reject inadmissible WAIT/control-flow, stale/skipped revisions and archived recipes, then call the already immutable/atomic `RecipeLibrary.save`. OFF-first valid drafts are labelled not START-eligible; even SET-first never authorizes physical START.
- Same module `inspect_native_document` and `publish_native_document`: accept only `{name, version, draft:{schema:1,base_recipe_id,execution_kind:"native_authority",overrides}}`, use existing `validate_native_draft`, real `VariableSpec` ranges/policies, `require_supported_native_execution` (unsupported-but-displayed fields rejected), and unchanged immutable `NativeRecipeDraftLibrary.save`. Wrong base identity / stale version rejected by that library.
- `tools/recipe_studio_offline.py`: CLI `check`, `save`, `check-native`, `save-native`; explicit input JSON file and **mandatory explicitly chosen library root for save**. No implicit node104/production path, remote API, charging session or network socket. Pure checks do not create any library files. JSON responses include validation status, identity, version, warnings and `physical_start_authorized:false`. Nonfinite JSON refused. Source of hardware limit values reused from `config.MAX_MANUAL_VOLTAGE` and `runtime.safety.variables.MAX_STAGE_CURRENT_A.default`, matching production `bot.py`.

Examples from repository root:
```sh
python tools/recipe_studio_offline.py check --file ./exported-step-recipe.json
python tools/recipe_studio_offline.py save --file ./exported-step-recipe.json --library-root ./scratch-recipes
python tools/recipe_studio_offline.py check-native --file ./native-draft.json
python tools/recipe_studio_offline.py save-native --file ./native-draft.json --library-root ./scratch-native-drafts
```
Saved JSON is compatible with the existing backend catalog/draft library, **not automatically deployed to node104 or activated**. PC HTML currently exports canonical step candidates (RS-1A); a fully interactive native UI and browser-to-library persistence are **future work**, not represented as finished. Import via CLI is a documented interim offline bridge, not the final PC UX.

Acceptance: `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q` on 12 selected recipe/native/visual/start/catalog regression files: **48 passed, exit 0, 52.20 s**. `git diff --check` PASS. New test files: `tests/test_recipe_studio_offline_import.py`, `tests/test_recipe_studio_native_import.py`. No node104, BW600, HA102, ESP, Output or firmware operation.

Next RS-1C: introduce friendly native parameter editor UI with `VariableSpec` metadata exported by the **existing** backend; create a browser-save transport only after verifying existing operator ACL binding, without adding a public network listener or second charge executor. P0 manual mode physical validation remains independent and high priority.

## 2026-11-09 — Recipe Studio RS-1C: native parameter UI backed by the canonical metadata registry

**Status: SOURCE-TESTED, not deployed.** The existing browser editor `tools/recipe_visual_editor_prototype.html` now has an additional native-recipe panel beside the separate step-program panel. It selects all **12 canonical variants** (Ca/Ca/EFB/AGM × normal/recovery/conditioning/diagnostic), displays owner descriptions/units/defaults/min/max/type, permits overrides only for parameters actually executable by production stage owners, imports/exports versioned `{name,version,draft}` documents supported by the existing `NativeRecipeDraftLibrary`, and marks non-executable settings read-only. Previous step recipe editing remains separate. No device command, recipe START, new actor/service, new local network listener, new ACL or duplicate configuration registry.

**Canonical metadata** is built in `runtime/charge/programs/recipe_studio_native_catalog.py` from `native_recipes()`, `native_recipe_parameters()`, actual owner `VariableSpec` and each one-parameter draft passed through `validate_native_draft` + `require_supported_native_execution`. The browser loads generated `tools/recipe_studio_native_catalog.js`, produced by `tools/recipe_studio_offline.py catalog-native --output tools/recipe_studio_native_catalog.js`. Static catalog is a **generated UI snapshot, never the validation authority**; after any change in native specifications, regenerate it. `tests/test_recipe_studio_native_ui.py` asserts byte/semantic parity to current Python, so drift fails tests rather than silently presenting stale limits. A focused JS module `tools/recipe_studio_native_editor.js` implements rendering, input checks and JSON round-trip; the existing HTML remains source of layout and has no second embedded native rules registry.

**Usage:** open `tools/recipe_visual_editor_prototype.html` from PC on HOME-PC; use the new section 'Копия штатного интеллектуального рецепта' and 'Экспорт копии JSON'. To check and save selected file via **existing** backend: `python tools/recipe_studio_offline.py check-native --file native.json` and `python tools/recipe_studio_offline.py save-native --file native.json --library-root ./scratch-native-drafts`. Using a test library (not production) is intentional; no browser-to-node104 publish, not yet final 'Save' button. A new immutable version is chosen explicitly; stale or wrong-parent revisions are rejected by the already existing native library. Browsers can reject wrong types/out-of-range/unknown input locally but final Python admission also checks cross-field combinations and excludes unsupported policies.

**Acceptance:** `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q` for `tests/test_recipe_studio_native_ui.py` and 8 native/user recipe/visual/start/UI regression modules: **45 PASS, 0 FAIL, 47.21 sec**, `node --check` for both newly generated catalog and native editor + HTML inline script PASS; `git diff --check` PASS. Tests execute real JS via Node sandbox with synthetic DOM; catalog diffed to canonical Python. Production node104 remains D144 slot16 COMMITTED code source `3f50133`, unchanged and untested physically by this source-only stage.

**Next RS-1D:** make local authenticated browser→library persistence through already available operator boundary, reusing `publish_step_document` / `publish_native_document` and existing catalog; first choose an existing safe user-facing process/ACL, not a new public or network service. Regression must test race/stale version, real reload and isolated state. P0 manual-control physical validation remains separately outstanding.

## 2026-11-09 — D151: START failure after reinstall, retained OVP/OCP zero-clear defect

**Operator evidence:** Telegram screenshot around 11:13 user local / 01:13 UTC on 2026-11-09, EFB 60 Ah recovery START rejected, Telegram displayed `output enable command returned false`. Live pinned SSH on node104 read-only: service `active/running`, PID237957, NRestarts=0, D144 slot16 installed source 3f50133 (historical sealed identity), `state/rd_control_mode_v2.json` mode `pb_managed`. Exact journald 01:12:50–01:13:24 UTC:
- START accepted 01:12:52; V/I programming 01:12:54–55; setpoint readback 01:13:01.
- Safety lease armed 01:13:02, generation204, remaining~899.7s, Modbus age~1.23s.
- **01:13:04 START refused: cannot retire old ovp=16.60**.
- Output OFF commanded and freshly confirmed 01:13:09; lease disarmed 01:13:11; subsequent OFF proofs 01:13:15 and 01:13:21, disarm 01:13:16/22.
- Final generic UI reason `output enable command returned false` is secondary to the explicit OVP retirement error.
- Independent fresh D150 direct ESP Native + HA post-failure read-only returned exit0: `ha102_output_off=true`, `esp128_output_off=true`, `active_session=false`, `edge_lease_armed=false`, fresh Native callbacks and distinct source nonces. No output activation/retry was requested during diagnosis.

**Source cause:** in `hass_api.py::_retire_unrequested_protection_limits` the installed code treats old protections OVP/OCP as disposable when new request doesn't explicitly include them, writes `set_ovp(0.0)` or `set_ocp(0.0)`, and requires V2 readback of zero. This is the exact path that returned false with old OVP 16.60 V; the underlying reason why the edge/HA refused the zero write is not yet independently proven. It is not safe to regard the absence of an explicit phase limit as a request to disable protection. Prior tests expected zero, hiding the defect.

**Source-only repair:** same single HassClient/ExecutionPort START owner now replaces retained protections, while fresh confirmed Output OFF, with bounded per-session targets `Vset + PROTECTION_OVP_MARGIN_V` and `Iset + PROTECTION_OCP_MARGIN_A` (existing module-owned margins, 0.10 V and 0.10 A). Each inferred limit is subjected to existing SafetySupervisor preflight and absolute voltage/current/protection ceilings; no extra authorization, alternate actuator, new config or independent protection owner. Any absent V2 readback, failed setter, invalid safety envelope, missing fresh OFF proof, or failure to converge to the new protected readbacks within 10s fails closed without sending Output ON. Explicit recipe OVP/OCP are unchanged. Crucial real-world EFB example: Vset14.82, Iset6.00 -> candidate OVP14.92 and OCP6.10, **to be confirmed physically**.

**Regression:** `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests/test_hass_safe_output_gate.py tests/test_live_transition_interlock.py tests/test_managed_runtime_safety.py tests/test_runtime_safety.py tests/test_recovery_resume_output_transaction.py` -> **85 passed, 0 failed, exit0, 47.67s**. Updated old regression that expected disabled 0.0 OVP/OCP; new physical-edge-like fake rejects 0.0 writes yet permits bounded positive limits; independent scenarios reject set command and stale ACK/no-readback, both preserve no Output ON. Source-only tested; not installed to node104, not physically accepted; no firmware/ESP/HA commands and no user START retransmission.

**Next:** independent focused code review + production D145/D144 upgrade with newly pinned exact source only after fresh canonical admission/backup and explicit safe operator deployment approval; re-run direct ESP Native and HA readback and perform controlled physical START only after upgrade under supervision. Never edit node104 files in place, bypass D145 or claim the code fix alone restored charging.
## 2026-11-09 — D152 follow-up: is OVP/OCP=0 a supported disable command?

Owner correctly challenged the D151 fix: should determine whether protections can be **disabled at the start**, avoiding conflicts during MAIN→MIX, before relying on per-phase targets.

**Source-confirmed root cause of the 2026-11-09 01:13:04 UTC failure** is upstream of the physical RD6018: `runtime/safety/runtime_guard.py::set_ovp` and `set_ocp` explicitly reject `requested <= 0`. The installed `hass_api.py::_retire_unrequested_protection_limits` sends `set_ovp(0.0)` and `set_ocp(0.0)`; hence the wrapper returns `False` and logs `cannot retire old ovp=16.60`. **The refusal does not prove** that ESPHome/Modbus or the Riden hardware firmware refuses zero. The prior D151 note's phrase 'physical edge may reject it' was a hypothesis; this guard rejection is established by exact code. The source-only D151 repair avoids zero by writing bounded protection targets and checks V2 readback, but no physical MAIN→MIX acceptance yet, and its behavior is not a proof that per-stage OVP/OCP cannot conflict.

**Public references:** Riden RD60xx UniSoft custom firmware reference (https://device.report/m/8a8fbfa06ae71aa02f3066894034f57ab11198f808da180b3f26fde2e9dc9800) explicitly states `OVP=0`, `OCP=0` disable corresponding software protections **for UniSoft custom firmware**. EEVblog user reports testing `OCP=0` on own RD6018 running UniSoft and the front panel blanks its OCP value: https://www.eevblog.com/forum/testgear/ruideng-riden-rd6006-dc-power-supply/1100/ . Official Riden manuals explain programming OVP/OCP via front panel but have not yet established the zero disable semantic for **node104 RD6018's exact device firmware**. Repo `esphome/rd6018.yaml` registers at Modbus holding 82 OVP, 83 OCP, both `min_value:0` on ESPHome numbers. This proves UI/firmware adapter accepts numeric zero at this layer, not that hardware disables reliably.

**Operational caution:** Simply relaxing the runtime guard to allow 0 would disable a protective layer on a live high-voltage Ca/Ca/EFB MIX charging system, and the existing SafetySupervisor START policy, runtime monitor, phase execution and readback expectations must be reviewed together. No command to write 0, START, flash or remotely edit node104 was executed. Confirm hardware firmware version and V2 semantics by read-only sources first. A guarded *offline* simulation of MAIN→MIX→safe-wait with explicit phase protection targets and verified readback is preferable to disabling both protections before a physical test. The existing current-setting CC regulation must never be presented as equivalent to separate protective OCP, and lease/thermal shutdown are independent safety controls.

**Decision pending physical test, not silently applied:** either retain positive phase-bounded OVP/OCP with correct transition sequencing (raise OVP before raising Vset; reduce I and settle before tightening OCP/OVP), or investigate firmware-specific zero disable solely in controlled hardware-off bench tests with a safe load and independent hardware limits. Do not remove safety gates or install zero semantics on node104 on documentation evidence alone. Source-only D151 commit 90cf2f8 remains local, uninstalled.

## 2026-11-09 — D153: OVP/OCP zero command admitted in guard only with confirmed OFF (source-only)

Owner instruction: "го разрешать 0", following documented investigation of the conflicting zero-rejection in `runtime/safety/runtime_guard.py`. Implemented minimal bounded acceptance in **existing** `RuntimeSafetyGuard.set_ovp/set_ocp` only (no second authority): `0.0` is an allowed value **only if Output OFF is positively observed** with fresh authoritative heartbeat (prefer `output_state_code_v2`, and require timestamp age ≤300 s). Invalid/negative/over-ceiling values remain rejected. Writing zero while ON or unknown does not forward a protection command; existing active-output fail-closed/OFF path remains. This is a firmware-specific **register command allowance**, not evidence that stock RD6018 firmware implements 0 as 'disable', nor physical proof the protective function is off. Hardware write on node104 NOT attempted. Tests cover OFF success, active ON failure, unknown/stale OFF, contradictory authoritative V2 ON, and negative values.

**Critical separation of behaviors:** D151 source-only `HassClient._retire_unrequested_protection_limits` still installs bounded **positive** protective OVP/OCP targets at START and confirms readback; it was **not** changed here to disable protections automatically. Stage transitions through MIX still require separate proof for OVP/OCP sequencing. Allowing zero with Output ON would disable independent protection during potential high-voltage battery charging and is deliberately not implemented. No change to hardware safety lease (900 s), charge currents/voltages, MIX, actuator hierarchy or production node104. Do not represent guard acceptance as 'OVP/OCP disabled at startup' until the full disable flow is designed and physically proven on this exact firmware.

**Acceptance:** `PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests/test_d153_zero_protection_off_only.py tests/test_hass_safe_output_gate.py tests/test_managed_runtime_safety.py tests/test_recovery_resume_output_transaction.py tests/test_runtime_safety.py tests/test_live_transition_interlock.py` — 90 PASS, 0 FAIL (49.38 seconds), `git diff --check` PASS. The five direct zero tests are in `tests/test_d153_zero_protection_off_only.py`. Current installed node104 is unchanged, no startup, firmware, flash or local HA/ESP side effects.

## 2026-11-09 — RS-1D local browser→canonical library persistence (source-only)

**Status:** implemented on HOME-PC source branch; not deployed on node104 and never sends device commands. The existing HTML `tools/recipe_visual_editor_prototype.html` gains **«Проверить в библиотеке» and «Сохранить новую версию»** buttons for **both** step SET/OFF/WAIT and native parameter copies. There is no second charger or recipe executor. Actions use new browser-only `tools/recipe_studio_save.js` and existing native editor UI to call an **explicitly started, short-lived localhost bridge** `tools/recipe_studio_local.py`. It invokes only `inspect_step_document/publish_step_document` or `inspect_native_document/publish_native_document` from the existing canonical implementation. Save returns the identity/version/readback digest or native base, and `physical_start_authorized=false` in all cases. No START/STOP/output/HA/ESP/firmware routes exist; backend does not import hardware execution.

**Launching from HOME-PC:** double-click `E:\CODEX\rd6018_bot\tools\start-recipe-studio.cmd`. This starts a transient Python server from the existing WSL Ubuntu-24.04 environment, opens `http://127.0.0.1:8768/studio`, and keeps the terminal alive only while the local editor is in use. The chosen scratch storage path is `E:\CODEX\rd6018_bot\.recipe-studio-local\` (mapped to /mnt/e...), separated into `steps/` and `native/`; this directory is gitignored. Browser opened as `file://` cannot save, because the bridge is required. Closing the terminal stops the bridge. If port 8768 is already used, launching fails visibly rather than silently picking a public port.

**Browser boundary:** HTTP binds only `127.0.0.1`, verifies Host, same-origin POST Origin, JSON Content-Type, short-lived random capability token via custom header, 256 KiB input limit; no CORS wildcard. The sensitive `studio-config.js` token is given only to a same-origin subresource fetch from `/studio` with `Sec-Fetch-Site: same-origin` and exact local Referer, to prevent foreign websites loading it as a JavaScript tag. Files served from fixed allowlist; no arbitrary files, templating, shell exec, arbitrary destination paths or actuator interfaces. Every save uses the *same* original immutable library and production schema/preflight; result reload is verified. A thread lock serializes local saves; version mismatch and no-overwrite hardlink publication reject duplicate/stale revisions. The local token is not equivalent to the Telegram operator ACL and is **not** used for remote/prod exposure. Existing native `VariableSpec` generated catalog remains read-only display; Python validation authoritative.

**Acceptance:** 50 PASS, 0 FAIL on browser bridge, native PC UI, canonical conversion, offline importer, preflight, atomic-save and START-selection regression; `node --check` for all edited JS and extracted inline HTML script; `git diff --check` PASS. `tests/test_recipe_studio_local_bridge.py` verifies both kinds, save→readback, immutable v1/v2, repeated/stale writes, CSRF/Host/Content-Type, token leak via cross-site script, path traversal, absent hardware routes. No GUI browser automation yet; DOM/JS tests remain in Node. Runtime node104 still prior installed D144 source; hardware mode P0, physical START, MAIN→MIX, and zero OVP/OCP firmware semantics are separate outstanding tasks.

**Next:** RS-2 operator-facing history/version selection, archive/revision comparison, and user-friendlier rendering for step recipes, using this same local boundary and canonical library. Do not turn the local bridge into a persistent production service or silently upload local recipes to node104. Physical P0 START/mode acceptance is still urgent and independent.


## 2026-11-09 — RS-2: local recipe history, immutable revision load, diff and archival

**Status:** RS-2 source implemented and offline verified; node104, HA102, ESP, firmware, physical output and running production untouched. The existing PC HTML now contains the "Библиотека рецептов · версии и архив" panel; user can select step/native collection and recipe, inspect all historical version numbers, load a chosen saved version into the **same existing editor** as an unsaved `latest+1` draft, compare arbitrary existing versions via safe textual diff, or archive with explicit browser confirmation. Archived history remains readable and comparable but cannot be opened for editing or receive new versions. Step visual import uses existing `visualFromCanonical`; native import uses existing `inspectDraft`; neither re-implements the charging algorithms.

**Authoritative owners reused:** `RecipeLibrary` and `NativeRecipeDraftLibrary` for load/versions/save, `RecipeCatalog` for step list/archive, `NativeRecipeDraftLibrary.archive` for native archival (added to the same owner), `runtime/charge/programs/recipe_studio_history.py` as pure read/diff dispatcher only. Both `RecipeLibrary.save` and `NativeRecipeDraftLibrary.save` reject new revisions when `.archived` exists; prevents bypass through direct calls by editor components. Historical `vN.json` bytes are never changed. `tools/recipe_studio_local.py` adds only `/api/list`, `/api/load`, `/api/compare`, `/api/archive` behind the existing localhost Host/Origin/capability-token check, fixed JSON shapes and explicit identity fields; no arbitrary paths or actuator endpoints. `tools/recipe_studio_save.js` and `tools/recipe_studio_history.js` implement browser UI; the same `tools/start-recipe-studio.cmd` remains the entry point, using isolated `.recipe-studio-local/` storage.

**Behavior:** `load` returns the exact immutable existing revision and the browser chooses `latest+1`; saving still requires canonical Python validation and same library optimistic version policy, so stale/racing saves are refused. `compare` performs canonical sorted-key JSON diff (version label excluded from content, preserving meaningful parameter changes), up to 24000 output characters. Archive is permanent from this UI (readable, no delete); no silent restore or deletion. PC-local scratch library does not replicate to node104 or modify pinned sessions. Native source selection remains fixed across revisions. Dynamic MAIN/MIX are not mapped into primitive SET/OFF steps.

**Acceptance:** WSL Ubuntu 24.04 pytest for 11 Recipe Studio, step/native admission, visual canonical bridge, atomic save, catalog, preflight, native draft library and START selection regression modules: **67 PASS, 0 FAIL, 63.61 seconds**. JavaScript syntax checks: `recipe_studio_history.js`, `recipe_studio_save.js`, `recipe_studio_native_editor.js`, and extracted HTML inline script PASS. `git diff --check` PASS. End-to-end HTTP tests in `tests/test_recipe_studio_history.py` cover two native/step revision chains, exact readback, compare, archival preserving bytes, read-only archive, direct-library bypass rejection, invalid paths and unsupported production endpoints and same-origin credential boundary.

**Next:** RS-3 Telegram user-friendly UI on the existing `runtime/ui/telegram/recipes.py` and `recipe_buttons.py`: version history and copy/edit/save next revision, reuse canonical stores, preserve one Telegram panel lifecycle. Physical P0 manual control, START/OVP/OCP zero semantics and MAIN→MIX transition tests remain outstanding and are independent of this source-only recipe editor effort.

## 2026-11-09 — RS-3A Telegram version navigation, copy and archival

Source-only improvement in **existing** `runtime/ui/telegram/recipe_buttons.py`; no new Telegram UI owner, service, ACL or charge executor. Individual step recipe panel now includes inline actions "История версий", "Копировать", "В архив". History is paginated (8 per page), loads immutable versions via existing `recipes:view:` route, and preserves Telegram callback 64-byte size cap. Copy calls existing `RecipeCatalog.duplicate` with generated `copy_<random>` name, creates independent v1 and routes to established step editor. Archive requires a separate confirmation/cancel callback, calls `RecipeCatalog.archive`, does not alter version bytes and prevents further edits via the canonical `RecipeLibrary.save` guard from RS-2. Existing `app._check_chat_and_respond` applies to all operations, and all responses explicitly avoid physical START. Native recipes remain their independent catalog; no native execution altered.

**Acceptance:** `tests/test_recipe_telegram_history_buttons.py` + `tests/test_recipe_real_callback_chain.py`, `tests/test_unified_recipe_catalog_ui.py`, `tests/test_user_recipe_catalog_pagination.py`, `tests/test_user_recipe_editor_pagination.py`, `tests/test_recipe_empty_preview_entry.py`: **12 PASS, 0 FAIL**, ~26.5 sec. Includes chain history→duplicate→archive-confirm, unchanged source versions, archive blocking new versions, 18-version pagination, Telegram callback max64, refusal for missing source, denied-chat mutation. `git diff --check` PASS. Not installed to node104; local source development only.

Next: RS-3B native user-copy Telegram browser, safe revision through existing `NativeRecipeDraftLibrary` with supported-override validation and no new persistence channel; then independent RS-4 acceptance. Production physical D151–D153/START and MIX transition remain separate outstanding work.

## 2026-11-09 — RS-3B native Telegram copy/browser and strict supported override check

Extends the existing `runtime/ui/telegram/recipe_buttons.py` owner; no second router or service. The 12 canonical native variants now offer a "Создать свою копию" button. This creates a non-energizing draft `copy_<10hex>` v1 through the **same** `NativeRecipeDraftLibrary` object used by the registered `/native_copy` and `/native_set` commands (passed into `install_recipe_buttons`). Adds "Мои копии штатных программ" listing and versioned read-only view with up to 10 recent versions. Callback length <=64 bytes is enforced for dynamically generated buttons; very long names are not presented as oversized callback payloads. Each callback uses the canonical chat ACL and returns no hardware activation or execution grants.

**Important correction:** Telegram `/native_set` previously called only `validate_native_draft` before `save`, allowing syntactically/range-valid overrides unsupported by the production stage owners. It now additionally calls `require_supported_native_execution`, matching Recipe Studio local/CLI and START admission. Existing immutable version semantics and archive guards stay owned by the same native library.

**Acceptance:** `tests/test_recipe_telegram_native_drafts.py` + `tests/test_recipe_telegram_history_buttons.py`, `tests/test_recipe_real_callback_chain.py`, `tests/test_unified_recipe_catalog_ui.py`, `tests/test_user_recipe_catalog_pagination.py`, `tests/test_user_recipe_editor_pagination.py`, `tests/test_recipe_empty_preview_entry.py`: **15 PASS, 0 FAIL**, 29.74 seconds. Confirmed native copy, readback and view, denied chat, missing canonical native ID, step history/copied/archive workflow and callback pagination. `git diff --check` PASS. Not deployed to node104 or connected to physical RD6018; still source-only.

**RS-3 overall:** step buttons history/copy/confirm archive (RS-3A), native canonical program copy and draft view (RS-3B). Editing native parameters continues through `/native_set`, creating immutable revisions, now with supported-execution check. A dedicated inline native parameter adjustment UI remains possible for later UX iteration, not marked complete. Next RS-4: integration/regression of PC and Telegram stores, preserve pinned selection, verify no START/output routes and prepare source release with install/rollback plan; physical P0/START/MIX remains a separate urgent gate.

## 2026-11-09 — RS-4 integration gate 1: unified source regression after RS-3

RS-3A committed `b0fa187`; RS-3B committed `cf32156`. After both, a unified source-only 17-module Recipe Studio/Telegram integration run exercised browser local history/API, native and step immutable stores, version archive and readback, visual JSON bridge, offline admission, Telegram ACL and real callback chains, native supported-override guard, preflight and START selection. Command:
`PYTHONPATH=tools:.:tests PYTHONDONTWRITEBYTECODE=1 /home/home-pc/.venvs/pcp-test/bin/python -m pytest -q tests/test_recipe_telegram_native_drafts.py tests/test_recipe_telegram_history_buttons.py tests/test_recipe_studio_history.py tests/test_recipe_studio_local_bridge.py tests/test_recipe_studio_native_ui.py tests/test_recipe_studio_native_import.py tests/test_recipe_studio_offline_import.py tests/test_recipe_visual_canonical_bridge.py tests/test_user_recipe_atomic_save.py tests/test_user_recipe_catalog.py tests/test_user_recipe_preflight.py tests/test_native_recipe_draft_library.py tests/test_native_recipe_start_selection.py tests/test_recipe_real_callback_chain.py tests/test_unified_recipe_catalog_ui.py tests/test_user_recipe_catalog_pagination.py tests/test_user_recipe_editor_pagination.py`
**Result: 81 PASS / 0 FAIL, exit 0, 81.99 s**. Clean working tree before this note, branch `feature/main-mix-countdown-display` ahead of owned origin by 13 commits. No node104/HA102/ESP actions or charging hardware actuation.

Remaining RS-4 release boundaries: review/validate PC browser UI with a real browser on HOME-PC; confirm that the two local scratch libraries are isolated from production; release package/update plan, compatibility and rollback with the established node104 D144/D145 mechanism; independent physical START/MAIN→MIX/OVP-OCP zero-write and PB_MANAGED↔HANDS_OFF acceptance. No production PASS or installation solely from source tests. User-approved plan continues without redesign, extra authorizations or duplicate engines.


## 2026-11-09 — MAIN/MIX operator journal source acceptance (not node104 deployment)

On HOME-PC feature branch `feature/main-mix-countdown-display`, journal/HMI telemetry source code commit `c70a6de38efbd6de8540ae09e6c3b40d4d524805` extends existing controller evidence with readable MAIN→MIX reason and thresholds, new-fact Imin/Vmax/Delta evidence, actual recipe finish-hold duration, a MIX progress message at the **existing** 10-minute checkpoint, and session-aware temperature source/age/status provenance. Fail-closed read-only formatting never substitutes a measured RD regulation mode. One execution owner and existing charge algorithm/safety remain intact. Source regression 212/212 PASS, separate D177 synthetic dry-run 31/31 PASS (different not-merged worktree). See `docs/assistant/RD6018_JOURNAL_TEMPERATURE_DRYRUN_2026-11-09.md` for exact coverage/limitations. Node104 and battery were untouched, temperature disagreement 25°C physical vs 23°C Telegram still requires fresh direct ESP Native readback and simultaneous secondary HA. No release/firmware/Output actuation or GitHub publication occurred at this checkpoint.
## 2026-11-10 — standalone RD6018 Wake R7.2 connector (source only)

Added a separate `integrations/rd6018-wake-connector/` package with a
read-only snapshot contract, strict event normalization, allowlisted fields,
stable event IDs, a size/age-bounded SQLite outbox, retry backoff, external
per-chat route validation, config schema/example, isolated systemd template,
and mocked tests. The connector service reads only an operator-provided
read-only diagnostic snapshot file and persists locally. It does not import
the bot runtime or use actuator/ESP/HA write paths.

Audit boundary: D106 (`tools/node104_d106_live_observer.py`) and D151/D091 are
read-only OFF/release proof collectors; D106 rejects active persistent charge
sessions, so neither is a suitable periodic source during the owner-reported
active charge. The exact R7.2-capable call found in the existing HOME-PC
launcher is `notify_r72_complete.py`, which represents Codex task completion.
It is deliberately not used for RD events. No generic R7.2 producer/ACK query
is exposed by current MCP tools or found in the accessible documented
interfaces. Outbound transport is therefore disabled; events remain local.
No ACK or delivery claim is made.

Focused package tests: `python3 -m unittest -v test_connector.py` — **8
passed**. This verifies parser/normalization, route validation, secret-field
exclusion, dedupe/restart persistence, retry timing, invalid-route hold,
submitted-vs-acknowledged state distinction, config permissions, and
snapshot symlink/size refusal. No live source, R7.2 transport, SSH, ESP, HA,
node104 service, or charger was accessed. Owner reports charge actively
running; D144 slot18 source `7c40e54` remains untouched. This package is not
ready to install/enable until an admitted live-charge-safe source interface
and supported generic R7.2 submission/ACK contract are supplied.

## 2026-11-10 — Event Gateway producer scope correction (source only)

The Wake Bridge 7.2 project chat owns Event Gateway, Dispatcher and the R7.2
transport adapter. RD6018 owns only the generic producer event contract and a
bounded local spool. This entry supersedes the preceding connector design
where it mentions chat route validation, local delivery retries/ACK states,
or concrete HA polling. Those responsibilities and integrations are absent
from the corrected producer.

`integrations/rd6018-wake-connector/connector.py` now defines the exact
universal envelope, strict UTC/UUID/source/type/severity validation,
allowlisted bounded payload, deterministic UUIDv5 occurrence identity,
persistent local dedupe, `pending_gateway` / `gateway_accepted` /
`quarantined_unknown` states, and an injectable `EventGatewayClient` protocol.
Gateway acceptance is not chat delivery. There is no HTTP client, guessed API
path, route configuration, delivery retry or ACK orchestration. The temporary
source adapter remains a bounded snapshot file; no HA request or node access
was made. README documents the missing published API contract and adapter
checklist.

This work is local source and mocked tests only. Connector tests: 10 PASS;
`py_compile`, JSON parsing, cache cleanup, and `git diff --check` PASS. The
uncommitted source diff is against base HEAD
`663d1051004a1e31c77d00d3a6bcf70ae3e02048`; no commit SHA exists. No node104,
HA, ESP, service,
deployment, charger, D144 slot18, state/config, output, or lease was accessed
or changed. `.git` is mounted read-only in this workspace: `git fetch origin
feature/main-mix-countdown-display` could not write `.git/FETCH_HEAD`; the
currently displayed tracking ref is at the base HEAD but live origin state is
unverified. Commit/push remain unavailable from this workspace.

## 2026-11-10 — Event producer source check

Producer-only scope: Wake Bridge profile chat owns Gateway, Dispatcher and R7.2; this repo awaits its API contract. Connector tests **10 PASS**, `py_compile`, JSON parsing and `git diff --check` PASS; package `__pycache__` removed. No node104 or deployment/hardware access. Branch `feature/main-mix-countdown-display`, base HEAD `663d1051004a1e31c77d00d3a6bcf70ae3e02048`; sole remote is expected `origin` URL, but `.git` is read-only so commit/push and fresh remote comparison are blocked. Local changes remain uncommitted.

## 2026-11-10 — read-only HA source adapter follow-up (SOURCE ONLY, HOLD)

Correction to the preceding connector notes: this follow-up implements an
independent `integrations/rd6018-wake-connector/ha_source.py` adapter that
reads the canonical `config/physical/ha102.yaml` entity map and performs only
GET state requests. It does not import the production HA transport, use any
switch/number control entity, or implement service calls/WebSocket commands.
It uses only `RD6018_WAKE_HA_URL` and `RD6018_WAKE_HA_TOKEN`; no `HA_TOKEN`
fallback exists. TLS verification, bounded responses, timeouts, strict
sensor-domain allowlisting, freshness provenance, separate internal/external
temperature fields, and bounded no-follow session metadata parsing are
covered by mocks. A typed adapter-attested snapshot is consumed by the
existing local spool service. No production application code was changed.

The `main_current_guard_v1` mapping is limited to schema/revision/snapshot
shape and a small fault-category allowlist. It does not expose guard
internals, session/battery IDs, or raw journal data. Missing HA timestamps
produce unknown freshness; `last_updated` is used only as a documented
conservative fallback. The first fresh snapshot after an unknown/stale episode emits one telemetry-recovered event.
Stale session metadata is ignored using the declared bounded
`session_max_age_s` setting (24-hour default). No optional systemctl query was
added.

Validation: connector suite **16 PASS**; package Python compilation, JSON
parsing, and `git diff --check` passed. Tests use mocked transports/files and
made no network, SSH, HA, systemd, ESP, or node104 calls. Exact code HEAD is
still base `663d1051004a1e31c77d00d3a6bcf70ae3e02048`; these changes remain
uncommitted. Deployment remains explicitly **HOLD** pending independent
review, dedicated least-privilege HA identity, and the unresolved generic
Wake producer/ACK contract. No node104 runtime, secrets, D144 slot18,
service, charge, firmware, or physical interface was accessed or changed.


## 2026-11-10 — HA source adapter hardening (LOCAL SOURCE ONLY)

Review of the mocked adapter tests found and corrected edge cases: HA redirects
are refused to prevent forwarding the bearer token; entity IDs must be unique;
naive or future-dated timestamps cannot prove freshness; implausible numeric
readings are rejected rather than clamped; and the raw output-state code is
preserved as a code instead of being misrepresented as a boolean. Internal and
external temperatures are both required core measurements and remain separate.

The stage occurrence timestamp from the canonical session file is used only
for deterministic event identity and is excluded from the event payload.
Unknown source periods are deduplicated across polling intervals, persisted
across restart, and followed by one recovery event when a fresh snapshot
returns. The heartbeat reports successful telemetry freshness, not output-ON.

The systemd template now creates its private mode-0700 state directory.
Installation still requires a dedicated non-admin HA identity with read-only
access to the exact allowlisted entities and a narrowly scoped read-only
group/ACL for charge_session.json. No file permissions, credentials,
services, production runtime, or hardware were changed. Validation remains
mock-only; deployment remains HOLD.

Final local validation: 21/21 connector unit tests PASS; py_compile PASS; config example and JSON schema parse PASS; git diff --check PASS. All HA responses were mocked. No live HA request, node104 access, deployment, firmware operation, or charger interaction occurred.


## 2026-11-10 — MAIN Guard setpoint ACK and missing-session recovery correction (SOURCE ONLY)

Corrected the misleading legacy current_ocp wording: the MAIN Guard ratchet transaction is an Iset/current-setpoint acknowledgement path; it does not establish an OCP trip. New quarantine reasons use main_guard_current_setpoint_transaction_unconfirmed; retirement validation continues to accept the old prefix solely for already-persisted incidents.

The durable quarantine reason now retains bounded electrical evidence from the failed postflight ACK: requested Iset, Native Iset readback, delta, configured readback tolerance, measured current, and ages of the required Native observations. No session/battery identifiers or credentials are added to the diagnostic string.

Fixed the /recovery_clear dead end for the authentic case where charge_session.json has already been removed by the controller but the strict active quarantine journal still retains the original session/battery/incident identity. The absent-session path is permitted only when the controller is IDLE with no in-memory session identity, the journal binding exactly matches the requested incident, and the reason is the MAIN Guard current-setpoint transaction (including the legacy persisted prefix). It does not synthesize or restore charge_session.json. The coordinator still requires the explicit private-chat operator confirmation and a fresh typed Native Output-OFF receipt; only then does the existing quarantine journal owner write its schema-2 retirement tombstone. Finalization rechecks the committed tombstone and IDLE/no-session state before releasing the in-memory quarantine.

The existing-session retirement path remains unchanged. Unknown/corrupt journal, mismatched incident/session/battery, non-IDLE controller, or missing fresh OFF evidence remain fail-closed. No OCP control/readback was reinstated.

Validation: focused recovery/MAIN Guard cohort 107 PASS, 18 subtests PASS before the additional diagnostic test; expanded cohort after the follow-up MAIN Guard signature cleanup 157 PASS, 2 deselected, 85 subtests PASS. Two tests were deselected only because this Windows runner cannot create symlinks (WinError 1314) and the other uses a Linux-only path/encoding assumption. The full suite cannot be collected on Windows because release tooling imports Linux-only fcntl/grp modules; re-run full regression under the project's Linux/Python 3.11 environment before release. py_compile and git diff --check PASS. No node104 files, HA, ESP, service, charge state, Output, lease, or D144 slot were changed. Production deployment remains HOLD; this is source-only until Linux regression and exact release admission are complete.


## 2026-11-10 — MAIN Guard is Iset-only; remove stale OCP contract

Owner correction applied: OCP was already removed from the MAIN Guard control contract and must not be reintroduced as an Iset-ratchet companion. The previous source still carried stale OCP arguments in the MAIN Guard commit/readback and verified-desulfation-return APIs. Removed those arguments and the corresponding test fixture expectations. MAIN Guard now admits/commits a reduction using the measured-current and Native Iset evidence only; the verified desulfation return likewise checks current-setpoint reset and fresh Output-OFF evidence without an OCP readback parameter. Updated production comments/log wording and the checkpoint/shadow descriptions so they no longer label this Iset-only operation as Iset/OCP.

Scope is deliberately limited to MAIN Guard. This does not change independent hardware trip telemetry, RuntimeSafetyGuard, or explicit recipe-owned MIX protection. No protection actuator was added and no OCP setter/readback was reinstated in MAIN Guard.

Validation in isolated WSL Python 3.12:
- MAIN Guard/recovery focused cohort: 140 PASS.
- Full pytest tests: 3199 passed, 2 failed, 3 skipped (475.65 s).
- The two failures are the same pre-existing operator UI state=None failures on the parent baseline (operator_managed_stop.py, test_operator_actions.py::test_keyboard_renders_logical_actions_without_runtime_objects, and test_operator_hmi.py::test_idle_safety_denial_does_not_hide_charge_workspace_navigation). Parent baseline full suite: 3189 passed, 3 failed, 3 skipped; its third failure was D149 router pin matching, which is fixed in the current branch. Thus the current full run has no new failure relative to the parent baseline and has ten additional passing tests.
- py_compile and git diff --check: PASS.

Source-only. No service, ESP, HA, charge session, Output, setpoint, lease, node104 or D144/D145 slot was touched. Production deployment remains HOLD pending the established release admission and physical acceptance.


## 2026-11-10 — RD6018 read-only event observer / R7.2 delivery status

The standalone observer implementation is committed locally as `5cc1bf9` on `feature/main-mix-countdown-display` (branch one commit ahead of the displayed origin tracking ref at inspection). It reads existing node104 SQLite sensor history, bounded state documents, service status and journal; it has no charger control path. Polling is 20 seconds internally, but normal summaries are rate-limited to at least 1800 seconds; fault/guard/service/telemetry transitions and mode/stage changes are event-driven with persistent duplicate suppression and separate recovery events.

Focused observer + connector suite: **31/31 PASS** on HOME-PC WSL. This does not prove installation, activation or delivery.

Operator's preceding handoff reported the observer staged but inactive on node104, Gateway at `192.168.1.110:8765`, node104 TCP + `/healthz` PASS, and producer binding to that preceding chat. These are retained as reported evidence only. In this chat, trusted R7.2 self-inspection returned `OWN_ENABLED_ROUTE_UNAVAILABLE`; the panel opener alone is not route proof. A read-only SSH attempt to node104 from WSL returned `Permission denied (publickey,password)`, so current service state, installed hashes, token-file presence/mode and node104→Gateway health remain unverified.

**HOLD:** do not activate the observer or enqueue a test event until this chat's own enabled route is confirmed and node104 read-only access is restored. Never borrow a route from another chat, print token values, replay an uncertain event, or modify RD6018/ESP/HA/charge state. After the gates pass, use one harmless unique event and require exact event-ID/route/attempt/ACK correlation before claiming delivery.

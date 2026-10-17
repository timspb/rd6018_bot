# RD6018 Bot V3 Project Runbook

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

Production VM104 was not touched and no hardware commands were sent.

Next exact boundary:

`ERADICATION-07: UI cutover`.

Migrate screens one at a time to canonical `ViewModel`, `ScreenSpec`,
`ButtonSpec`, `UIAction` and application intents. Remove each historical
callback only after parity. Gate: canonical UI imports no historical
runtime/controller/HA/ESP modules.

## 14.13 ERADICATION-08 checkpoint - 2026-10-05

Boundary: ERADICATION-08: runtime/composition cutover.

Pre-boundary authority:
- ERADICATION-07 functional HEAD b5e5bff8328d187cd1ddb9c012f2be69e783a4fe;
- GitHub Actions run #1564 / 37228622855: Python 3.10/3.11/3.12 PASS;
- ERADICATION-07 documentation handoff HEAD 80881a978b4b7bf9286477f075493885102af909.

Exact local ERADICATION-08 code HEAD:
517521d30b3708ab6d8366a200bdb587623b5164.

The production entrypoint now has one explicit composition owner and lifecycle:

- bot.py remains the only production entrypoint and is a distinct module object;
- sys.modules aliasing is removed;
- bot.py no longer writes its main function back into runtime.v2_runtime;
- every compatibility installer call is inside ProductionComposition.compose();
- module top level performs one ProductionComposition(...).compose() call;
- startup authority reconciliation, physical test-control start/stop, runtime
  startup and cancellation are owned by ProductionComposition.run();
- main() is a thin delegate to the composition lifecycle;
- transitional module-level _rd_*, _legacy_main and startup-recovery aliases are removed;
- compatibility reads use a read-only __getattr__ bridge through composition.runtime;
- runtime.v2_runtime remains the encapsulated compatibility substrate and is
  intentionally deferred to ERADICATION-09.

Installer order and accepted runtime semantics are unchanged.

Local validation on exact code HEAD 517521d30b3708ab6d8366a200bdb587623b5164:

- entrypoint/composition ownership: 13/13 PASS;
- startup-authority integration: 2/2 PASS;
- restart/restore HA composition: 1/1 PASS;
- Phase 6 composition root: 5/5 PASS;
- Phase 6 architecture guardrails: 6/6 PASS;
- legacy inventory: 4/4 PASS;
- production physical isolation: 2/2 PASS;
- autonomous install-order contract: 4/4 PASS;
- V1 UI compatibility: 9/9 PASS;
- python -m compileall -q .: PASS;
- git diff --check: PASS;
- filtered CI-equivalent full discovery: 1915 PASS, 2 skipped;
- test_manual_context_v2: 4/4 PASS separately.

The split full-suite execution is a local Python 3.14 teardown artifact:
test_manual_context_v2 reports all four tests PASS, but its process remains alive
after unittest completion. Total logical local coverage is therefore 1919 tests,
2 skipped, 0 failures. The authoritative remote gate remains GitHub CI on
Python 3.10/3.11/3.12.

Production VM104 was not touched.
Hardware commands sent: NO.

Remaining gate:
docs checkpoint -> push -> exact-head GitHub CI (3.10/3.11/3.12).

On CI PASS, close ERADICATION-08 as remote-verified and begin the final
ERADICATION-09: remove the historical production graph.
### 2026-10-05 ERADICATION-08 remote verification

Exact functional/documentation HEAD:
cbb5d157f82202a9db15e6c64a6ea62037d2f088.

GitHub Actions exact-head run #1566 / 37235184475 completed PASS:

- Python 3.10: PASS;
- Python 3.11: PASS;
- Python 3.12: PASS.

PR #29 points to the verified ERADICATION-08 branch head. Production composition
is now explicit and lifecycle-owned; sys.modules aliasing, module-level installer
execution and module-level composition aliases are retired. runtime.v2_runtime
remains only as the encapsulated compatibility substrate for the final
ERADICATION-09 boundary.

Production VM104 was not touched.
Hardware commands sent: NO.

Next exact boundary:
ERADICATION-09 - remove historical production graph.

ERADICATION-09 gate:
- no production import of runtime.v2_runtime;
- no historical FSM production import/reachability;
- no bot_legacy production execution;
- remove compatibility files only after archive/reference capture and proof that
  the production graph no longer reaches them.

### 2026-10-05 ERADICATION-09 checkpoint 1 - canonical production runtime identity

Pre-boundary authority:
ERADICATION-08 exact verified HEAD
`cbb5d157f82202a9db15e6c64a6ea62037d2f088`,
GitHub Actions run `#1566` / `37235184475`, Python 3.10/3.11/3.12 PASS.

Exact code HEAD for this increment:
`eff53c5d359afeb58584be9b5a17ae41ba446457`.

The first historical-graph edge is retired:

- `bot.py` imports `runtime.production_runtime` as the composition substrate;
- production sources contain no import edge to `runtime.v2_runtime`;
- `runtime/v2_runtime.py` is now a read-only compatibility facade over the
  canonical production runtime;
- `bot_legacy.py` is non-executable and read-only, with no `sys.modules`
  aliasing;
- production-oriented tests and source guards target
  `runtime/production_runtime.py`; dedicated compatibility coverage keeps the
  historical import name observable without granting it production authority.

Local validation for the structural cut:

- entrypoint/composition: 13/13 PASS;
- legacy inventory: 4/4 PASS;
- modular architecture contract: 9/9 PASS;
- execution convergence: 12/12 PASS;
- Manual/Custom eradication: 8/8 PASS;
- uptime synchronization: 5/5 PASS;
- canonical UI source/parity impact-set: 12 suites PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS.

Remote verification:
GitHub Actions exact-head run `#1568` / `37237082292` PASS on Python
3.10/3.11/3.12.

Closed ledger entry:
`L-001`.

ERADICATION-09 remains IN PROGRESS. Remaining exact debt:
`L-002`, `L-003`, `L-004`, `L-007`, `L-008`, `L-010`, `L-012`.

Next exact boundary:
remove residual historical controller/FSM reachability. Do not delete the
historical controller until PREP/COOLING/IDLE/DONE compatibility semantics are
owned by modular runtime services and `super().tick()` is unreachable.

Production VM104 changed: NO.


### 2026-10-05 ERADICATION-09 checkpoint 2 - START/recipe retirement

Exact functional HEAD: `547de140eb4c32a527c94bbc2c65a15cea5847e2`.

GitHub Actions exact-head run `#1574` / `37281527533` completed PASS on Python 3.10, 3.11 and 3.12. Local CI-equivalent discovery on the same code state: 1926 tests PASS, 2 skipped.

Closed at this checkpoint:

- L-004: production historical `super().tick()` fallback retired; unknown residual stages fail closed;
- L-007: legacy START runner/adapter retired from production; application START transaction service is authoritative;
- L-010: `legacy_recipe_adapter` removed; recipe mapping/authorization is owned by `application/recipe_policy.py` with existing recipe envelope semantics preserved.

Remaining ERADICATION-09 debt: L-002 compatibility installer stack, L-003 historical `ChargeController` superclass, L-008 legacy UI read-model adapter, L-012 legacy transition audit.

Production VM104 was not touched. No hardware commands were sent.


### 2026-10-05 ERADICATION-09 handoff — final two debts

Remote-verified functional checkpoint:

- PR #29 branch: `refactor/v3-modular-legacy-eradication`;
- exact functional HEAD: `309ea7ea9fcefea624291293b09d215df2b52bae`;
- GitHub Actions run `#1578` / `37285010255`: PASS on Python
  3.10 / 3.11 / 3.12;
- local documentation checkpoint above that functional state:
  `ea6200b1194b20232baeeea9d0adeb2052a33ee3`.

Work completed since the previous START/recipe checkpoint:

- operator read-model was detached from the historical runtime object;
- the legacy UI read adapter boundary was retired;
- the dead legacy transition-audit decision source was removed;
- L-008 and L-012 are therefore CLOSED;
- exact-head remote CI is green for the resulting functional state.

ERADICATION-09 now has only two architectural debts left:

- **L-002** compatibility installer stack;
- **L-003** historical `ChargeController` superclass reachability.

Current local worktree is intentionally dirty with the next contraction increment,
and must be preserved for continuation. It is extracting shared constants and
persistence values out of `charge_logic.py` so that superclass retirement can be
done without duplicating accepted semantics.

Current dirty/untracked scope:

- modified:
  `charge_controller.py`,
  `done_storage_restore.py`,
  `manual_mode.py`,
  `manual_runtime.py`,
  `manual_text.py`,
  `mix_active_authority.py`,
  `mix_current_containment.py`,
  `production_controller.py`,
  `production_guardrails_v2.py`,
  `runtime/charge/profiles/manual.py`,
  `runtime/production_runtime.py`,
  `runtime/safety/variables.py`,
  `runtime_safety.py`,
  `managed_runtime_safety.py`;
- untracked:
  `runtime/charge/persistence.py`,
  `runtime/charge/strategy/exit_variables.py`.

Intent of this dirty increment:

- `runtime/charge/persistence.py` becomes owner of `SESSION_FILE` and session
  restore-age policy;
- `runtime/charge/strategy/exit_variables.py` becomes owner of MIX ΔI/ΔV exit
  thresholds;
- `runtime/safety/variables.py` becomes owner of watchdog/high-voltage watchdog
  thresholds and OVP/OCP margins;
- production consumers stop importing those values from `charge_logic.py`;
- no target, timeout, margin or safety behavior is intentionally changed.

Required continuation order:

1. finish the current dependency-contraction diff without changing semantics;
2. run focused charge/manual/runtime-safety/persistence regressions;
3. run `python -m compileall -q .` and `git diff --check`;
4. run the full unittest suite;
5. commit/push the coherent increment and require exact-head CI 3.10/3.11/3.12 PASS;
6. statically enumerate what `ChargeControllerV2` still consumes from
   `ChargeController`;
7. migrate those residual helpers/state to modular owners, then remove the
   superclass edge (close L-003);
8. remove compatibility installers that become unreachable (close L-002);
9. prove the production graph has no historical FSM import/reachability;
10. archive/reference-capture remaining compatibility files before deletion;
11. full suite + exact-head CI, then close ERADICATION-09 and the overall
    ERADICATION-01…09 migration.

Do not restart the project audit. Repository state remains authority.
Do not touch VM104/production during this migration boundary.
Do not send hardware commands.


### 2026-10-05 ERADICATION-09 checkpoint 3 - charge_logic dependency contraction

The pre-L-003 dependency-contraction increment is complete locally.

Canonical ownership moved without changing accepted production values:

- `runtime/charge/persistence.py` owns `SESSION_FILE` and the 24-hour session-start age policy;
- `runtime/charge/strategy/exit_variables.py` owns the MIX CC ΔV and CV ΔI exit references (0.03 V / 0.03 A);
- `runtime/safety/variables.py` owns the 12.0 A stage-current ceiling, 0.1 V/A OVP/OCP margins, 300 s watchdog, 60 s high-voltage watchdog and 15.0 V high-voltage threshold.

Production consumers in the contraction set no longer import those values from `charge_logic.py`. A static regression guard verifies the exact accepted values and proves that `charge_controller.py` retains exactly one historical import edge: `ChargeController` itself.

The remaining inherited persistence writer is deliberate evidence for L-003: until the historical superclass is retired, inherited `_save_session()` still resolves `charge_logic.SESSION_FILE`, while V3 readers resolve the canonical persistence owner. Tests patch both identities only for this transitional superclass boundary.

Local validation:

- focused charge/manual/MIX/production/runtime-safety/persistence regression set: PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- CI-equivalent full discovery with repository CI environment: **1925 tests PASS, 2 skipped**.

L-002 and L-003 remain OPEN. This checkpoint does not claim superclass or installer retirement.

Production VM104 changed: NO.
Hardware commands sent: NO.

Next exact boundary after exact-head remote CI: build the actual inherited dependency inventory for `ChargeControllerV2(ChargeController)`, migrate only residual production dependencies to modular owners, and remove the superclass edge (L-003).


### 2026-10-05 ERADICATION-09 checkpoint 4 - L-003 inherited dependency inventory

The pre-mutation L-003 inventory is now explicit and regression-guarded.

Starting authority for this boundary:
- branch: `refactor/v3-modular-legacy-eradication`;
- exact starting HEAD: `0d9dc707469f689e35e0ccbdd2aac932a2e51e22`;
- GitHub Actions run `#1582` / `37307969815`: PASS on Python 3.10 / 3.11 / 3.12.

Static analysis of `ChargeControllerV2(ChargeController)` proves that the historical
`tick()` is not in the inherited production support closure. The remaining
superclass edge is support-only: initialization, start/stop lifecycle, session
persistence/restore, target helpers, temperature compensation, stage bookkeeping,
protection-limit helpers and compatibility state.

The exact inherited historical support closure is locked by
`tests/test_v3_l003_inherited_dependency_inventory.py`. It contains 29 methods
and rejects any expansion, especially re-entry of historical `tick()`.

The only direct historical import in `charge_controller.py` remains:
`from charge_logic import ChargeController`.

Validation for this characterization boundary:
- focused inventory tests: 2 PASS;
- `python -m compileall -q .`: PASS;
- `git diff --check`: PASS;
- CI-equivalent full discovery with workflow environment: 1927 PASS / 2 skipped.

No ledger item is closed by this checkpoint. L-003 remains OPEN until
`ChargeControllerV2` no longer inherits or imports historical `ChargeController`.
L-002 remains OPEN.

Next exact boundary: migrate the bounded support closure to modular owners without
changing accepted semantics, remove the superclass/import edge, add zero-reachability
guards, and require focused/full/exact-head CI before closing L-003.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 5 - L-003 controller state ownership cut

The first actual L-003 superclass contraction is PASS.

Starting remote authority:
- remote checkpoint: `c8ca6010a5af11e4128e20eb2aa1a8f20a3ba2c9`;
- GitHub Actions run `#1586` / `37321027512`: PASS on Python 3.10 / 3.11 / 3.12.

Cut completed:
- added `runtime/charge/controller_state.py` as the canonical owner for controller
  stage/profile identifiers and compatibility-shaped mutable state bootstrap;
- `ChargeControllerV2.__init__` no longer calls historical
  `ChargeController.__init__`;
- `current_stage` and `is_active` are now owned directly by
  `ChargeControllerV2`;
- all production-referenced stage/profile constants are explicitly owned by the
  V2 controller via the canonical state module;
- the historical superclass remains temporarily only for the still-bounded
  lifecycle/persistence/target/temperature/protection/bookkeeping support surface.

Regression guards were expanded to cover:
- exact transitive historical method closure;
- externally referenced inherited support surface;
- stage/profile constant ownership;
- state-shape parity against the historical constructor.

Validation:
- L-003 inventory/state tests: 5 PASS;
- `test_charge_controller.py`: 7 PASS;
- production-controller tests: 26 PASS;
- runtime-safety tests: 43 PASS;
- persistence tests: 17 PASS;
- CI-equivalent full discovery: 1930 PASS / 2 skipped;
- compileall: PASS;
- diff-check: PASS.

L-003 remains OPEN. Historical `tick()` remains absent from the inherited support
closure. Next cut: lifecycle/persistence support, then target/temperature/protection
and remaining bookkeeping, with zero-reachability guards before removing the
`ChargeController` import/inheritance edge.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 6 - L-003 bookkeeping and lifecycle contraction

The second L-003 contraction is PASS.

New modular ownership:
- `runtime.charge.controller_state` now also owns stage-sample bookkeeping,
  stage-metric reset, bank-fault reset, link-loss reset, restored-target clearing,
  and Delta/blanking reset;
- `runtime.charge.runtime.variables.DELTA_MONITOR_DELAY_S` canonically owns the
  accepted 120 second Delta monitor delay;
- `runtime.charge.lifecycle` owns start/start_custom session initialization,
  session-data reset, and stop mechanics.

Removed from historical inherited dependency:
- `_mark_stage_sample`;
- `_reset_stage_metrics`;
- `_reset_bank_fault_state`;
- `_reset_link_loss_state`;
- `_clear_restored_targets`;
- `_reset_delta_and_blanking`;
- `start`;
- `start_custom`;
- `_init_session`;
- `reset_session_data`;
- `stop`.

The historical superclass remains only for persistence/restore, target and
temperature/protection helpers, plus a bounded diagnostic/operator support set.
Historical `tick()` remains outside the dependency closure.

Validation after the combined state + bookkeeping + lifecycle contraction:
- L-003 inventory/state tests: 5 PASS;
- ChargeControllerV2 tests: 7 PASS;
- production-controller tests: 26 PASS;
- focused start/lifecycle tests: PASS;
- compileall: PASS;
- diff-check: PASS;
- CI-equivalent full discovery: 1930 PASS / 2 skipped.

Next boundary: persistence/restore extraction into the canonical session owner,
followed by target/temperature/protection support and final zero-reachability
removal of `charge_logic.ChargeController`.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 7 - L-003 persistence/restore extraction

Session persistence and restore are now owned by `runtime.charge.persistence`.

Retired from historical superclass dependency: `_clear_session_file`, `_save_session`, `try_restore_session`.

The transfer is mechanical from accepted behavior. Session age, AGM stages, Mix finish hold, maximum stage current, elapsed-clock sanity and Pb voltage clamp now resolve through their existing modular owners. Existing session-path semantics are preserved by explicit `session_file=SESSION_FILE` injection from `ChargeControllerV2`.

Validation: L-003 inventory/state 5 PASS; persistence-focused 17 PASS; ProductionChargeControllerV2 26 PASS; compileall/diff-check PASS; CI-equivalent full discovery 1930 PASS / 2 skipped.

Residual L-003: target/temperature/protection plus bounded diagnostic/operator helpers, then zero-reachability removal of `ChargeControllerV2(ChargeController)` and its historical import. Historical `tick()` remains absent.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 7 - target, temperature, and protection extraction

L-003 contracted again from starting local HEAD `93728a5e502079becd5a8aca3bfaab45e8cf5cc1`.

This boundary moved the remaining target-selection, temperature-compensation, and
phase-protection helpers out of the historical `ChargeController` inheritance
surface and onto modular owners:
- `runtime.charge.strategy.prep` and `runtime.charge.strategy.main_targets`
  remain target authorities;
- new `runtime/charge/strategy/temperature_variables.py` owns the accepted
  25 C reference, 0.60 V compensation cap, and Ca/EFB/AGM/Custom coefficients;
- `runtime.safety.variables` remains OVP/OCP/MAX-current authority;
- `runtime.charge.strategy.desulfation_variables` remains DESULFATION OCP margin authority.

`ChargeControllerV2` now owns compatibility-shaped adapters for:
`_add_phase_limits`, `_add_desulf_limits`, temperature compensation,
PREP/MAIN target selection, profile target selection, and restored-target selection.
No transition decision or hardware-write authority moved into these adapters.

The inherited transitive support closure shrank from 12 methods to 3:
- `_make_log_event_end`;
- `_post_charge_profile_params`;
- `_record_safe_wait_sample`.

The externally referenced inherited surface also shrank accordingly.

Parity proof:
- dedicated target/temperature/protection parity against historical controller;
- L-003 inventory/parity: 6 PASS;
- ChargeControllerV2 focused: 7 PASS;
- production-controller focused: 26 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1931 PASS / 2 skipped.

L-003 remains OPEN: historical superclass/import still exists for the residual
bookkeeping/report helpers and externally referenced utility surface.
L-002 remains OPEN.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 8 - zero transitive historical support closure

L-003 reached a new structural boundary: `ChargeControllerV2` no longer calls any
historical `ChargeController` helper transitively.

Moved from inherited historical support:
- post-charge profile thresholds now come from `runtime.charge.post`;
- SAFE_WAIT sample recording is local to the V2 compatibility surface and consumes
  the canonical post-charge profile owner;
- stage-end log payload construction is local and behavior-preserving.

Regression inventory now requires:
`EXPECTED_HISTORICAL_SUPPORT_CLOSURE = set()`.

Direct parity covers:
- post-charge profile thresholds for Ca/Ca, EFB, AGM, Custom;
- SAFE_WAIT sample cadence/state;
- stage-end log payload.

Validation:
- L-003 inventory/parity: 7 PASS;
- full CI-equivalent local discovery: 1932 PASS / 2 skipped;
- compileall/diff-check remained PASS in the preceding focused gate.

Important: L-003 is still OPEN. The superclass/import remains only because external
production callers still address a bounded inherited utility API surface. No V2
internal execution path depends on historical helper implementation anymore.

Next exact boundary: migrate the remaining externally referenced utility surface by
semantic owner, add zero-external-reachability guards, then remove
`ChargeControllerV2(ChargeController)` and the `charge_logic` import.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 9 - L-003 historical superclass retired

L-003 is CLOSED locally.

`ChargeControllerV2` no longer imports or inherits historical
`charge_logic.ChargeController`.

The final extraction moved the remaining externally referenced compatibility
surface to semantic V3 owners:
- stage/exit/timer compatibility helpers -> `runtime.charge.runtime.support`;
- emergency/full state reset -> `runtime.charge.lifecycle`;
- read-only diagnostics, timer and AI snapshots -> `runtime.charge.diagnostics`;
- CV Mix current-reversal ratio -> `runtime.charge.strategy.exit_variables`.

Canonical policy was preserved rather than copying stale historical conflicts:
- Ca/Ca active-Mix maximum: 20 h;
- EFB active-Mix maximum: 24 h;
- AGM active-Mix maximum: 10 h.
The old `charge_logic.py` EFB 20 h diagnostic/reporting text was not reintroduced.

Structural proof:
- historical transitive support closure: ZERO;
- external inherited production surface: ZERO;
- `charge_controller.py` charge_logic import edge: ZERO;
- `ChargeControllerV2` superclass list: empty.

Semantic proof includes controller-state parity, target/temperature/protection
parity, post-charge/log parity, canonical Mix exit/timer checks, and V2
diagnostic/bank-fault characterization.

Validation after physical superclass removal:
- focused L-003 inventory/parity: 9 PASS;
- ChargeControllerV2: 7 PASS;
- production controller: 26 PASS;
- auto strategy: 2 PASS;
- V2 production controller: 7 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1934 PASS / 2 skipped.

No VM104 mutation occurred and no hardware command was sent.

Next ERADICATION-09 boundary: L-002 only. Retire compatibility installers in
`ProductionComposition.compose()` strictly where zero reachability/redundancy is
proved; no aesthetic cleanup and no change to accepted production semantics.


### 2026-10-06 ERADICATION-09 checkpoint 10 - L-002 Manual-OFF wrapper retired

The first L-002 compatibility installer is retired from production composition.

Removed from `ProductionComposition.compose()`:
- `install_auto_manual_off_contract(_legacy)`;
- the corresponding `auto_manual_off_v2` import in `bot.py`.

The wrapper was proven redundant rather than merely old: its only production effect
was to force `manual_off_active=False` before delegating to
`ChargeControllerV2.tick()`. That invariant is now owned directly by the
production controller before stage-scaffold evaluation, while the persistent
Manual-OFF condition remains an externally evaluated asynchronous terminal stop.

Regression proof:
- dedicated Manual-OFF contract tests: 6 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1936 PASS / 2 skipped.

The compatibility module itself is retained for now as historical/reference code;
this checkpoint removes only its production composition edge. File deletion must
wait for the final archive/reference-capture gate.

L-002 remains OPEN because other compatibility installers still exist in
`ProductionComposition.compose()`. No other installer is removed by implication.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 11 - L-002 production guardrail wrapper retired

The second L-002 compatibility installer is retired from the production composition
graph.

Removed from `ProductionComposition.compose()`:
- `install_production_guardrails(_legacy)`;
- the corresponding `production_guardrails_v2` import from `bot.py`.

Its two real production responsibilities were migrated to explicit owners instead
of being dropped:
- Vin chemistry authority is statically disabled in `runtime.production_runtime`;
  `MIN_INPUT_VOLTAGE` remains a compatibility-shaped symbol with value `-inf`
  and Vin remains PSU-health telemetry only;
- durable Cooling continuation validation now runs directly inside
  `ProductionChargeControllerV2.tick()/try_restore_session()`, with pure token
  validation owned by `runtime.charge.runtime.cooling_guard`.

The SAFE_WAIT Cooling contract remains unchanged: its clock is frozen through
Cooling, Output stays OFF, and corrupt/missing continuation state fails closed.

Regression proof:
- direct guardrail/Cooling tests: 5 PASS;
- production entrypoint: 13 PASS;
- autonomous install-order contract: 4 PASS;
- runtime namespace contract: 3 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1936 PASS / 2 skipped.

The historical `production_guardrails_v2.py` file is retained only for
archive/reference capture and is no longer reachable from `bot.py`.

L-002 remains OPEN while other compatibility installers still patch the production
runtime at composition time.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 12 - L-002 Output readback wrapper retired

The third L-002 compatibility installer is retired from production composition.

Removed from `ProductionComposition.compose()`:
- `install_output_state_readback(_legacy)`;
- the corresponding `live_output_readback_v2` import.

Register-18 Output truth is now owned by the canonical telemetry normalization path:
`rd6018_telemetry.canonicalize_live()` promotes a valid binary
`output_state_code_v2` to the compatibility `switch` value and copies its
freshness metadata with `source_key=output_state_code_v2`.

This occurs inside `HassClient.get_all_live()` before runtime-safety captures its
raw reader, so managed, HANDS_OFF and safety paths share the same canonical Output
value/freshness without a late composition wrapper.

Regression proof:
- live freshness / Mix eligibility: 8 PASS;
- autonomous install-order: 4 PASS;
- runtime safety: 43 PASS;
- Hass-focused suite: PASS, exit 0;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1936 PASS / 2 skipped.

The historical `live_output_readback_v2.py` remains only for final
archive/reference capture and is no longer reachable from `bot.py`.

L-002 remains OPEN for the remaining composition-time compatibility installers.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 13 - L-002 Telegram bootstrap wrapper retired

The fourth L-002 compatibility installer is retired from production composition.

Removed from `ProductionComposition.compose()`:
- `install_telegram_startup_resilience(_legacy)`;
- the corresponding `telegram_startup_resilience` import.

Bootstrap resilience now belongs to the Telegram transport adapter itself.
`telegram.runtime.ResilientBootstrapBot` preserves the intentionally narrow
accepted retry semantics:
- `me()` retries only `TelegramNetworkError` with capped exponential backoff;
- `set_my_commands()` attempts once, then defers idempotent command sync on a
  transient Telegram network error;
- non-network exceptions are never swallowed;
- arbitrary send/edit/callback methods are not replayed.

`create_telegram_runtime()` constructs the resilient transport directly, so no
composition-time monkey patch is required.

Regression proof:
- Telegram bootstrap resilience: 4 PASS;
- Telegram runtime adapter: 5 PASS;
- production entrypoint: 13 PASS;
- V3 legacy inventory: 4 PASS;
- compileall: PASS;
- diff-check: PASS;
- stable full CI-equivalent local discovery: 1936 PASS / 2 skipped.

The historical `telegram_startup_resilience.py` file remains only for final
archive/reference capture and is no longer reachable from `bot.py`.

L-002 remains OPEN pending exact classification/retirement of the residual
compatibility installer stack. Canonical component/UI/ownership wiring is not
considered debt merely because its API is named `install_*`.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 14 - L-002 soft watchdog wrapper retired

The fifth L-002 compatibility installer is retired from production composition.

Removed from `ProductionComposition.compose()`:
- `install_soft_watchdog_containment(_legacy)`;
- the corresponding root compatibility import.

Canonical ownership now lives in:
- `runtime.safety.soft_watchdog` for bounded outage/authority decisions;
- `runtime.production_runtime.soft_watchdog_loop()` for the single periodic runtime task.

Accepted safety semantics are preserved:
- fresh heartbeat resets the incident;
- unresolved startup authority, HANDS_OFF, AUTONOMOUS and live release suspend Pb watchdog authority;
- idle/proven-OFF outage is passive;
- managed or last-known-ON outage requests existing hard-stop containment immediately;
- failed remote shutdown attempts are retried only at the bounded 60 s cadence;
- a successful shutdown latches the incident and prevents command storms.

Regression proof:
- canonical soft-watchdog tests: 11 PASS;
- autonomous composition: 2 PASS;
- production entrypoint: 13 PASS;
- runtime namespace contract: 3 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1937 PASS / 2 skipped.

The historical `soft_watchdog_containment.py` remains only for final
archive/reference capture and is no longer a production composition dependency.

L-002 remains OPEN. The next true compatibility-patch candidate is
`done_storage_restore`; canonical service/UI/ownership installers are not retired
merely because their public API uses an `install_*` name.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 checkpoint 15 - L-002 Done/Storage restore wrapper retired

The next L-002 compatibility installer is retired from production composition.

Removed from `ProductionComposition.compose()`:
- `install_done_storage_restore(_legacy)`;
- the corresponding `done_storage_restore` import from `bot.py`.

Its production responsibilities now belong to canonical owners:
- Done/Storage durable intent and restore authorization: `runtime.charge.persistence`;
- controller Done classification state: `runtime.charge.controller_state`;
- startup/auto-enable and operator-pause restore guards: `runtime.production_runtime`.

The accepted distinction between physically opposite Done states is preserved:
- explicit managed Storage Done persists `completion_kind=storage`,
  `output_intent=on`, and canonical Storage setpoints;
- legacy/ambiguous/terminal Done normalizes fail-closed to
  `completion_kind=terminal`, `output_intent=off`;
- normalization updates only Done intent/version metadata and does not rewrite
  previously captured terminal voltage/current/Ah evidence.

A regression discovered during extraction was fixed before closure: legacy terminal
Done normalization initially rewrote `terminal_metadata.voltage` with restore-time
telemetry. The canonical normalizer now preserves historical terminal evidence 1:1.

Regression proof:
- Done/Storage restore tests: 9 PASS;
- Done restore contract tests: 4 PASS;
- final SAFE_WAIT output transaction: 5 PASS;
- production controller: 26 PASS;
- compileall: PASS;
- diff-check: PASS;
- full CI-equivalent local discovery: 1937 PASS / 2 skipped.

The historical `done_storage_restore.py` file is retained only for final
archive/reference capture and is no longer reachable from production composition.

L-002 remains OPEN for remaining composition-time compatibility installers.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-06 ERADICATION-09 final local closure candidate

Local ERADICATION-09 implementation is complete.

L-003 is already closed: the historical `ChargeController` superclass and all
transitive/external inherited production reachability are gone.

L-002 is now closed locally. Six composition-time compatibility patchers were
retired after their semantics moved to canonical owners:
- Manual-OFF inertness -> V2 controller / terminal condition;
- Done/Storage restore -> canonical charge persistence/controller/runtime guards;
- Output register-18 promotion -> telemetry canonicalization;
- production guardrails -> production runtime + Cooling guard;
- soft watchdog containment -> canonical safety watchdog owner;
- Telegram bootstrap resilience -> Telegram transport owner.

The remaining `install_*` calls are not legacy debt: a static inventory explicitly
classifies the exact set as canonical domain, runtime/ownership, physical-validation
or operator-UI component composition. Any unclassified installer now fails the
architecture guard.

Before deleting the six unreachable compatibility source files, their exact Git
blob IDs, last source commits, and canonical replacements were captured in
`docs/ERADICATION_09_COMPATIBILITY_REFERENCE.md`. Git history remains the archive.

Final post-deletion local validation:
- focused architecture/namespace/behavior guards: PASS;
- compileall: PASS;
- `git diff --check`: PASS;
- full CI-equivalent discovery: **1936 PASS / 2 skipped**.

This is not yet the remote authority. PR #29 still points at remote head
`c8ca6010a5af11e4128e20eb2aa1a8f20a3ba2c9`. The final local tree must be
synchronized to the PR branch and exact-head GitHub Actions must pass on Python
3.10, 3.11 and 3.12. Only then may ERADICATION-09 be marked REMOTE-VERIFIED
COMPLETE.

Production VM104 changed: NO.
Hardware commands sent: NO.


### 2026-10-07 ERADICATION-09 remote closure and physical-evidence handoff

ERADICATION-09 is **REMOTE-VERIFIED COMPLETE**.

Remote authority:
- PR #29 head: `019a9fdf2ceb43438e380ec09fd37a5f323feb8d`;
- exact remote tree: `908fccf41e6bc7a2a12a2068952f028f5246bb00`;
- GitHub Actions run `#1588` / `37487373313`: Python 3.10, 3.11 and 3.12 PASS;
- PR #29 merged cleanly;
- resulting `main`: `4336e7c54ccb83d00445cf8f7950824dde141c57`.

The next canonical workstream is no longer legacy eradication. It resumes the
physical-evidence sequence from section 12:
1. fresh read-only dual-transport evidence;
2. independent ESP-direct `OFF -> ON -> OFF` only after the read-only gate passes;
3. HA control/readback latency characterization;
4. controlled charge bench only after both previous physical gates pass.

A new `tools/live_physical_smoke.py` command wraps the existing read-only
`LiveSmokeRunner`. It has no executor/gate/command dependency and emits only
sanitized evidence. Missing config, credentials, connectivity, snapshots or a
non-MATCH comparison returns `BLOCKED` with exit code 2.

Current HOME-PC preflight is **BLOCKED before physical execution**:
- HA102 TCP/8123 is reachable;
- ESP128 native API TCP/6053 is not reachable from HOME-PC;
- deployment HA/ESP environment values are not present on HOME-PC;
- no Output/setpoint/protection command was sent;
- node 101 was not accessed or changed.

Therefore the independent ESP-direct transition must not be attempted from the
current HOME-PC context until fresh dual-source read-only evidence is available.


### 2026-10-07 physical evidence checkpoint - source availability blocker

Fresh read-only preflight proves the current blocker is source availability, not
credential discovery or HA entity naming. Local credential sources were loaded
only into process memory and never printed.

Observed:
- HA102 API reachable and authenticated;
- all canonical RD6018 HA entities return `state=unavailable`;
- ESP128 canonical/static address is still `192.168.1.28`;
- that address does not answer ping or TCP 80/443/6053 from HOME-PC.

During this preflight a fail-open evidence defect was found and corrected:
`LiveSmokeRunner` no longer treats `connection_state=connected` as sufficient.
Bench-critical snapshot fields must all be present or the run is `INVALID`.

Result: physical continuation remains **BLOCKED**. The independent ESP-direct
`OFF -> ON -> OFF` run is prohibited until a fresh read-only smoke returns two
valid snapshots and a MATCH comparison. No node 101 access and no physical write
occurred in this checkpoint.


### 2026-10-07 physical evidence checkpoint - dual-source read-only PASS

After ESP128 was powered back on, the canonical read-only preflight was repeated from HOME-PC using existing local credential sources loaded only into process memory.

Fresh evidence:
- ESP128 (`192.168.1.28`) ping: PASS;
- ESPHome native API TCP/6053: PASS;
- HA102 snapshot: VALID;
- ESP128 snapshot: VALID;
- dual-source comparison: MATCH;
- Output: OFF on both sources;
- measured voltage/current: 0.00 V / 0.00 A on both sources;
- battery voltage: ~13.07 V on both sources;
- configured voltage/current: ~14.43 V / 9.00 A;
- OVP/OCP: ~14.53 V / 9.10 A;
- temperature: 28 C;
- physical writes sent: NONE.

The prior source-availability blocker is cleared. The next physical gate is the independent ESP-direct `OFF -> ON -> OFF` bench transition under the existing manual execution/ARM protocol. This checkpoint itself remains strictly read-only.


### 2026-10-07 physical evidence checkpoint - ESP-direct transition PASS

The independent ESP-direct physical gate is closed.

Fresh preflight: HA102=VALID, ESP128=VALID, comparison=MATCH, Output OFF,
current 0.00 A, battery about 13.07 V. The manual controlled-state-transition
path selected 13.57 V / 0.10 A with OVP 14.07 V / OCP 0.20 A, verified all
programmed readbacks, confirmed ON after 1.509 s, held for 10 s, then confirmed
OFF + 0.00 A after 2.531 s. Final dual-source post-check remained MATCH.

The executor had already been hardened and exact-head CI verified before this
run so that post-enable failures force verified-OFF containment and ON state is
polled within the bounded readback timeout.

Latency comparison with the earlier HA-ESP run (`1.526 s` ON / `2.546 s` OFF)
shows no meaningful HA penalty; the difference versus direct ESP is about
17/15 ms. The latency gate is therefore closed as downstream ESP/RD readback
propagation rather than HA overhead.

Next boundary: controlled charge bench readiness. Do not invent a new physical
charge loop; use only an existing canonical charge/start execution route after
its current readiness/ownership/rollback gates are re-evaluated against the
post-ERADICATION main.

### 2026-10-07 controlled chemistry charge bench

Operator-selected battery: `Leoch-72Ah`, Ca/Ca, 72 Ah, intent `recovery`.
Condition remains `unknown`; it was not inferred from terminal voltage.

Fresh START preflight PASS: ownership available, telemetry valid, safety allowed,
recipe `ca_ca:recovery`, ceiling 16.5 V, initial MAIN target preview 14.7 V / 7.2 A.

A bounded 30 s run executed through the current production START route after
managed startup-authority reconciliation. START returned `accepted=True`,
`reason=started`, trace `80f16fddcdad48b1a6f81975f6d66c64`.

Observed output stayed about 14.74-14.75 V while current tapered from about
3.82 A to 3.35 A. External temperature stayed 23 C; internal temperature rose
from 29 C to 30 C during the run.

The managed stop issued OFF. Strict edge-heartbeat confirmation timed out and
entered existing fail-closed containment, after which the fallback required
read-only OFF + 0 A before retiring the AUTO session. A fresh independent
HA102/ESP128 post-check then returned VALID/VALID/MATCH, OFF and 0.00 A.

Physical bench result: PASS. Residual: strict OFF heartbeat observability window
did not recognize the transition before timeout. Preserve freshness rules; fix
the evidence/latency mismatch rather than weakening OFF confirmation.

Evidence: `docs/V3_CONTROLLED_CHARGE_BENCH_EVIDENCE_2026-10-07.md`.

### 2026-10-07 production namespace normalization

Post-ERADICATION cleanup continues beyond compatibility-facade deletion.
Production-reachable module filenames were renamed away from the historical
`v2_*` / `*_v2` namespace without adding forwarding shims. The current names
include `production_bootstrap`, `production_bot_ui`, `charge_controller`,
`managed_runtime_safety`, `charge_authority`, `battery_catalog`, `battery_input`,
`mix_mode`, `manual_*`, `sg_*`, `ui_support`, and `ui_polish`.

The duplicate, unreachable `runtime/v2_startup_recovery.py` source is deleted;
production already uses `runtime.startup_recovery.StartupRecovery`. The Phase 9
comparison file is renamed to neutral `application/decision_comparison.py`.

A static namespace regression test rejects production Python filenames/imports
that reintroduce the retired module namespace. External ESPHome/readback entity
identifiers that contain `_v2` are protocol/schema names and are not runtime
ownership aliases.

Behavioral semantics, persisted charge policy and physical safety are unchanged
by this namespace pass. Full-suite and remote exact-head CI are required before
merge.


## 2026-10-07 production type normalization

The post-ERADICATION namespace cleanup now extends to current production types and
composition API. Historical type names such as `ChargeControllerV2`,
`ProductionChargeControllerV2`, `V2RuntimeSafetyGuard`, `V2RuntimeLifecycle` and
V2 START transaction DTO/adapter names are removed from production sources.
Current owners use neutral names (`ManagedChargeController`,
`ProductionChargeController`, `ManagedRuntimeSafetyGuard`,
`ProductionRuntimeLifecycle`, `StartTransaction*`, `StartEventContext`).

This pass does not rename persisted session keys, telemetry entity IDs or Telegram
callback-data tokens. Those values cross restart/UI protocol boundaries and require
explicit fail-closed migration rather than textual substitution.


## 2026-10-07 shadow/migration island eradication

Static import-graph analysis from `bot.py` plus an external-inbound scan proved a
closed shadow/migration cluster had zero callers outside the cluster. The cluster
included obsolete dual-runtime, decision-authority shadow/parity, telemetry and
configuration ownership rehearsal, staged-ownership, transition, shadow observer,
evidence/acceptance and legacy-domain adapter modules.

Because these modules were unreachable from production and tools, they were
deleted rather than renamed or wrapped. Phase/epic tests whose only purpose was
to characterize that retired island were deleted with it. The historical
Workstream-1 audit test was also removed because it asserted obsolete facts such
as `V2 remains execution owner` and `NOT READY FOR REAL OWNERSHIP TRANSITIONS`.
Historical audit documents remain evidence only and are not CI authority.

Current architecture guards now require the retired shadow/migration module set
to remain absent. No production behavior or physical safety semantics changed.


## 2026-10-07 historical charge FSM eradication

Operational-root reachability (production bot + tools + standalone CLIs) proved
`charge_logic.py` and its sole helper `legacy_safety.py` had no live inbound edge.
The historical FSM and safety compatibility source were deleted rather than kept
as dormant fallback code.

Tests that exercised only the historical controller were deleted. Current manual,
Mix, recovery, persistence, diagnostics and fail-closed tests were retained and
rewired to current owners; parity-with-legacy inventory was replaced by direct
absence/ownership guards. No current production source imports either historical
module.

External persisted/session keys are unchanged in this pass. Physical/electrical
safety semantics remain owned by current strategy/safety/execution modules.


## 2026-10-07 application contract island eradication

Operational-root reachability (production bot, standalone CLIs and tools) proved
a closed application/presentation compatibility island had zero inbound edges.
The retired island contained phase-era actuator/containment/configuration/domain
contracts, alternate application composition/lifecycle, old dry-run/start adapters,
old Telegram adapter/panel-store and old presentation panel modules.

The island was deleted rather than wrapped. Phase/epic tests whose only subject
was that island were removed. The live `application.execution_intent` contract and
`application.execution_port` were explicitly retained because the physical
execution owner imports and uses them. The remaining operator read-path and
implicit-runtime-start checks were rewritten as current runtime guardrails.

No production route, execution semantics, persisted session state or hardware
behavior changed in this boundary.


## 2026-10-07 root compatibility eradication

Operational-root reachability proved the remaining root compatibility set
(`first_stage_evidence.py`, `live_recovery_bridge.py`,
`mix_current_containment.py`, `rd_operation_mode.py`, `recipe_output.py`,
`recovery_orchestrator.py`, `recovery_runtime.py`) had zero live inbound edges.

The first-stage re-export was removed after tests were moved to the canonical
`runtime.charge.evidence.first_stage` owner. The other modules and their direct
characterization tests were removed rather than preserved as dormant fallback
paths. Architecture guards now require these root compatibility files to remain
absent.

No live production route, persisted session key or hardware behavior changed in
this boundary.


## 2026-10-07 final bot runtime bridge eradication

The production entrypoint `bot.py` is now composition-only. Its temporary module
`__getattr__` delegation to `runtime.production_runtime` is removed, composition
locals no longer use `_legacy`, and the lifecycle dependency is named
`runtime_main`. Runtime controller/router/HASS/UI state must be imported from the
canonical runtime owner directly rather than read through `bot`.

Regression coverage requires the bridge and `_legacy`/`legacy_main` terminology
to remain absent from `bot.py`. No actuator, safety, persisted-state or physical
behavior changes are part of this boundary.


## 2026-10-07 staged runtime skeleton eradication

The unused Phase-era runtime container was removed after proving zero production
and tool callers. Deleted surfaces include `runtime.app.RuntimeApp`,
`RuntimeDependencies`, the duplicate generic lifecycle manager, and the
`runtime.application` context/orchestrator/lifecycle package. The package root
`runtime.__init__` no longer provides lazy compatibility exports.

Live leaf components were retained and tested directly: `ChargeService`,
`ChargeStateProvider`, and replay models/runner/comparator. Replay tests now use
an injected minimal orchestrator contract instead of retaining the dead staged
application container. Production `ProductionRuntimeLifecycle` is unchanged.

No production execution, physical safety, persisted-state, Telegram protocol,
or hardware behavior changed in this boundary.


## 2026-10-07 legacy charge adapter retirement

`runtime.charge.adapters.legacy.LegacyChargeProgramAdapter` had zero production
or operational callers and was only exercised by its own characterization test.
The temporary adapter and its public package export were deleted. Historical
Phase 4D/4E documents remain evidence only and are not current runtime authority.


## 2026-10-07 residual legacy adapter retirement

Post-ERADICATION caller analysis showed the remaining UI/action/diagnostic/bank-fault/
hardware/execution-policy legacy adapters had zero production or operational callers.
Only characterization tests and package exports kept them alive. Those adapter surfaces
and parity-only tests were removed while live UI commands, diagnostics scoring, physical
bridge interfaces and execution policy remain unchanged.


## 2026-10-07 current documentation authority normalization

The root `README.md` was still an active-documentation defect after the code cleanup: it described the retired V2 cutover as production, advertised removed compatibility files and a historical branch, and presented deleted legacy ownership as current architecture.

The root README is now a concise current-production entry document. It points to the V3 runbook/modular architecture/fail-safe/deployment authorities, describes the explicit modular ownership path, and makes physical execution a separate authorization boundary. It does not resurrect migration-era V2/V1 modules or rename persisted/protocol identifiers.

`docs/README.md` now explicitly treats the eradication ledger as completed historical proof rather than a source of new runtime authority. Runtime code, physical behavior, persisted state, node 101 and hardware are unchanged by this documentation-only boundary.


## 2026-10-07 internal V2 semantic identifier cleanup

Production filenames/types were already normalized. This pass removes residual
internal owner terminology such as `v2_owner` and stale "preserved V2 owner"
wording from the application execution/START boundaries. The application-scoped
physical port now exposes `execution_owner`; the frozen actuator call inventory
was updated only for that identifier rename and the exact set of physical call
sites is unchanged.

Persisted `v2_*` session keys, Telegram callback-data tokens, the `V2_UI` external
configuration flag and deployed ESPHome/entity identifiers are intentionally not
changed here because they cross restart/protocol boundaries. They require separate
state/protocol migration contracts.


## 2026-10-08 active architecture authority normalization

Post-ERADICATION code authority is now reflected in the active agent/composition/modular architecture documents. `AGENTS.md` no longer directs contributors to deleted V2/legacy runtime owners or migration rollback switches. The composition-root document no longer labels the live bootstrap as transitional, and the modular architecture document is classified as the current production contract rather than a future migration target.

Historical-looking persisted/session, Telegram callback-data and deployed ESPHome/entity identifiers remain explicit protocol/state boundaries; this documentation pass does not rename them or alter runtime semantics.

Runtime code, node 101, physical execution and hardware behavior are unchanged by this boundary.


## 2026-10-08 node104 controlled acceptance checkpoint

The current-main software-normalization boundary was deployed to production host
node104 only. The deployed application marker is
`5cd8cfe083b8e211f5acd34cb21005103a583973`; the existing
`rd6018-bot.service`, service user, `.env`, configuration directory and virtual
environment were preserved. A pre-handover application backup and rollback tree
were created before the handover. Remote compileall and the complete 1570-test
unit suite passed; exact-head GitHub Actions run 1654 also passed on Python
3.10/3.11/3.12.

The fresh node104 read-only HA102/ESP128 snapshot was valid and agreed: both
reported Output OFF, 0 V and 0 A. With conservative bench values (13.57 V,
0.10 A, OVP 14.07 V, OCP 0.20 A), controlled HA-ESP and ESP-direct
OFF -> ON -> OFF transitions both completed with bounded readback and terminal
Output OFF. HA lease renew/disarm readback passed. A deliberately armed lease
expired during a controlled service-stop test; the edge reported lease tripped,
kept Output OFF, and remained OFF after service restart. The final independent
node104 snapshot remained HA/ESP MATCH, Output OFF, 0 V and 0 A. Node101 was not
accessed, and no ESPHome firmware or application authentication boundary was
changed.

This is a checkpoint, not a completed production acceptance. The actual
operator/application START -> STOP route was not executed because this run had
no interactive operator callback session. The repository's opt-in physical-test
control socket could not be activated under the existing service hardening:
`ProtectSystem=strict` caused the `/run` bind to fail closed, and a temporary
runtime-only `/run` allowance still left the socket inaccessible to the service
user. Therefore controlled stale/unavailable-telemetry and post-enable
verification-failure injections through the production application remain open.
No hardening was weakened and the service was restored to its normal unit at the
end of the checkpoint. The required terminal state was independently verified:
Output OFF, near-zero V/I, lease disarmed/tripped containment retained, service
active, and the deployed SHA exact.

## 2026-10-10 node104 acceptance continuation — blocked at hardened socket boundary

The local checkpoint was fast-forwarded without discarding work to exact merged
`origin/main` `8db6a904254c261bce51313df42a61b913b2657a` (PR #57 head
`8fcdab9373c68496f794076b5d8f770c11edec1f`). Exact-head CI was green on Python
3.10, 3.11 and 3.12. Focused local charging-log and physical-control suites
passed (`5` and `13` tests; `3` physical-control skips).

The production unit was inspected on node104 only. It remains `ProtectSystem=strict`,
with its original `ReadWritePaths` and no permanent environment changes. A temporary
opt-in physical-control activation was attempted using the existing socket-path
override, first under the service state directory and then under a systemd-managed
runtime directory with a narrow bind/read-write exception. The process failed closed
at `asyncio` socket bind with `OSError: [Errno 30] Read-only file system` in every
location; no physical-test operation or actuator command was reached. The temporary
drop-in, socket paths and restart state were removed. The service returned `active`
with its normal environment, no test socket, and normal polling logs.

The remaining stale/unavailable-telemetry, post-enable verification-failure and
operator START→STOP acceptance gates therefore remain unexecuted. No physical PASS
is claimed. The explicit `RD6018_STATE_DIR` history-path resolution change is local
only and is not deployed or merged while this acceptance blocker remains.

## 2026-10-10 node104 acceptance continuation 2 - deferred lease fix and stop

The narrow production-state and deferred-edge-lease fixes are committed locally
as `6f2ff85` and `e18c3fde4e22e619e1c2f860bfa9e05bc3f8304c`. Local validation
passed: `python -m compileall -q .`, `git diff --check`, focused edge-lease and
physical-control tests, and the complete suite (`1573` tests, `OK`, `3 skipped`).
The branch is two commits ahead of `origin/main` `8db6a904254c261bce51313df42a61b913b2657a`.

The exact merged application was deployed to node104 with the pre-existing
service and `ProtectSystem=strict`; the charging history path was corrected to
the service state directory. The deferred lease fix was then installed as a
bounded node104 acceptance artifact after a file backup. The service remained
`active`; temporary physical-test configuration was removed again and the unit
was restarted with `DropInPaths=` empty. No change was made to node101.

The physical sequence was stopped before any energization. The production
socket client first failed closed with `edge lease reader unavailable`; after
the local fix it did not return a bounded independent live snapshot and
timed out while reading the external HA/lease state. There was therefore no
authorized fresh OFF snapshot suitable to precede ON, no proven non-battery
bench load, and no interactive operator callback for START -> STOP. No stale
telemetry injection, post-enable verification-failure injection, or real
operator START -> STOP was run. No actuator ON command was issued by this
acceptance continuation.

GitHub publication of the two local commits failed with `Invalid username or
token`; consequently no new PR/CI result exists and merge/final production
acceptance cannot be claimed. The terminal node104 service state was observed
as `active`, `ProtectSystem=strict`, and normal drop-in state restored. Final
hardware Output OFF/V/I evidence for this continuation is not claimed because
the bounded live snapshot was unavailable; this is an external acceptance
blocker, not a PASS.

## 2026-10-10 software-only node104 acceptance checkpoint - HA sidecar factory fix

Root cause confirmed for the deferred lease-binding failure: production config
selects `default_connector=esp_direct`, but `HassClient.from_physical_config()`
constructed `HassClient("", "", backend=connector)`. The ESP-direct backend
therefore supplied physical telemetry and actuator methods, while the same
client had no HA URL/token for `get_state()`, so `EdgeSafetyLease` could not
read the six HA lease entities after deferred startup. The node104 observation
provided with this checkpoint showed the HA endpoint reachable and ESP-direct
telemetry valid with Output OFF; no node access was performed during this
software-only change.

The narrow fix in this checkpoint retains the configured `HA_URL` and
`HA_TOKEN` in the client while keeping the selected connector as
`_physical_backend`. Existing dispatch remains physical-backend-first for
`get_all_live()` and actuator writes; HA REST is only the lease/read sidecar.
The regression tests cover sidecar state reads plus physical telemetry,
factory credential retention, and deferred lease binding with lease enforcement
still enabled. HA URL selection was reviewed in `config.py`: `HA_LOCAL_URL` is
used only when deployment configuration enables `HA_PREFER_LOCAL`; no runtime
configuration or secret was changed.

Software evidence on the local worktree: focused composition and edge-lease
suites passed (`5` and `8` tests); `python -m compileall -q .` passed;
`git diff --check` passed; complete unittest discovery passed (`1576` tests,
`3` skipped) on local Python `3.14.0`. No physical acceptance, CI result,
node104 modification, service restart, Output ON command, or node101 access is
claimed.

## 2026-10-10 native ESPHome safety-lease migration checkpoint

The `esp_direct` physical connector now owns the lease read/command path through
the native ESPHome Noise API. The six lease states are read from the subscribed
native entities with source/type/freshness metadata, and the renew, disarm, and
HANDS_OFF-release buttons are invoked by native ESPHome key/device identifiers.
The existing lease authority still requires generation change, armed/tripped and
quarantine checks, fresh direct Modbus age, and a replenished 900-second lease;
renewal cadence remains 300 seconds. Missing, stale, unknown-type, disconnected,
or rejected native state fails closed. HA REST is retained only as a compatibility
sidecar when the selected connector does not provide native methods.

Read-only node104 discovery confirmed the six states and three buttons on
`192.168.1.28:6053`, with 66 entities and no services. Native readback was
available for all six states; the observed state was unarmed, tripped, boot
quarantine clear, generation 2, fresh Modbus telemetry, and zero remaining time.
No lease button or actuator command was sent, no Output ON was attempted, and
node104 was not restarted or modified. This is software CODE PASS plus native
discovery evidence, not physical bench validation or production deployment
acceptance; exact ESPHome compile/flash and the D061/D062 bench gate remain the
next production prerequisite.

## 2026-10-10 native safety-lease production acceptance — blocked before deployment

PR #58 remained open at Python commit `65cf7ba86fbb52c4c912a5aa82a7cd1f97310e6b`;
the branch was not merged or deployed. The canonical repository firmware target
was compiled locally with ESPHome `2026.8.2` and the existing local secrets. The
exact compile succeeded for ESP8266 `esp01_1m`; the resulting local binary was
518688 bytes with SHA256
`4EE6ACE28E9C916FCAB3D15FF6F7B37231D9AEA3D6F4D1761AC495A8CE916E86`.
No flash or OTA was performed.

The read-only native API identity of `192.168.1.28:6053` is
`rd6018-controller`, MAC `C8:2B:96:30:FD:A5`, ESPHome `2026.8.2`, project
`timspb.rd6018-pb-recovery-v2`, version `2.0-edge-adoption`, compilation time
`2026-09-10 19:50:14 +1000`. The repository source currently declares project
version `2.2-autonomous-authority`, so the compiled candidate is not evidence
that the installed image is the same image. The installed node exposes 66
entities and 0 services, including the lease, autonomous, protection and live-
adoption contract entities.

Independent read-only snapshots were taken from both HA `192.168.1.102:8123`
and native ESPHome. They agreed on terminal Output OFF / 0 V / 0 A and native
readback showed protection code `0`, lease unarmed, lease tripped, boot
quarantine clear, generation `2`, fresh Modbus age about `6.1 s`, and remaining
lease `0 s`. No lease button, actuator command, restart or flash was issued.
The HA lease timestamps were stale relative to native ESP telemetry; this is
expected evidence for the direct native path, not a physical D061/D062 pass.

At that checkpoint, production acceptance was blocked because the node104
service/deployed SHA could not be read (the generic SSH authentication attempt
was rejected), and absence of a dangerous external load / safe bench
authorization was not independently proven. Access was recovered in the later
read-only audit below. Therefore no production
deployment, Output ON, START/STOP, renew/disarm/HANDS_OFF operation, stale-data
injection, or post-enable failure test was attempted. Node101 was not accessed.

## 2026-10-10 node104 SSH recovery and read-only runtime audit

Authorized access was recovered using the existing HOME-PC
`SFTP_RD6018_BOT_104_*` profile and its configured private-key identity through
Paramiko, with the target checked against the existing OpenSSH `known_hosts`
store. The prior `Permission denied` was caused by the earlier generic
`root@node104` attempt not using this profile: the Windows SSH config has no
node104 host stanza, the SSH agent is unavailable in that shell, and the saved
profile was not loaded into its environment. No key/password was printed or
changed. The authorized SSH account reports `uid=1000(debian)` and hostname
`rd6018-bot`; node101 was not accessed.

The required read-only acceptance commands passed on node104:

- `hostname` -> `rd6018-bot`
- `id` -> `debian`
- `systemctl is-active rd6018-bot` -> `active`
- `systemctl show rd6018-bot -p MainPID -p ProtectSystem -p DropInPaths` ->
  MainPID `27497`, `ProtectSystem=strict`, empty `DropInPaths`

The live unit is `/etc/systemd/system/rd6018-bot.service`, runs
`/opt/services/rd6018-bot/venv/bin/python /opt/services/rd6018-bot/app/bot.py`
with working directory `/opt/services/rd6018-bot/state`, service user
`rd6018`, and writable paths limited to state/logs/backups. The executable is
Python 3.11.2. systemd reports `NRestarts=0`; the current service activation
began `2026-10-09 15:48:17 UTC`. No restart or service/configuration change was
performed during this audit.

The root-owned `/opt/services/rd6018-bot/.deploy_sha` marker reports
`5cd8cfe083b8e211f5acd34cb21005103a583973`. A read-only Git-blob comparison of
the deployed production modules found a mixed source tree rather than a clean
checkout of that marker: `physical_test_control.py` and
`runtime_safety_strict.py` match `e18c3fde4e22e619e1c2f860bfa9e05bc3f8304c`,
while the other checked changed runtime files (including `hass_api.py`,
`edge_safety_lease.py`, `runtime/config/loader.py`,
`runtime/physical/connectors/esp_direct.py`, and
`runtime/physical/transports/esp128.py`) match the `5cd8cfe` marker tree.
Consequently `5cd8cfe` is the deployment marker/base SHA, not a claim that the
entire live working tree is exactly that commit. The active `bot.py` contains
the `ProductionComposition` entrypoint.

The running config root is `/opt/services/rd6018-bot/app/config`. There is no
`RD6018_CONNECTOR` process override; `config/physical/connectors.yaml` selects
`esp_direct`. The actual deployed `ESPHomeTransport` predates the PR #58 native
lease implementation and has no `get_entity_state()` native lease reader.
Moreover, the deployed `HassClient.from_physical_config()` returns a client
with empty HA URL/token while `EdgeSafetyLease` still needs `get_state()` for
its lease evidence. Thus the running Python application is not ready to consume
the native ESPHome lease contract; the HA-sidecar correction and native reader
on PR #58 are not deployed at the marker SHA. Any missing lease evidence must
remain fail-closed; do not infer readiness from service `active`.

A fresh read-only ESPHome Native API query to node104's configured controller
completed using the deployed Python environment; it sent no entity/button or
RD6018 control command. Device identity was `rd6018-controller`, project
`timspb.rd6018-pb-recovery-v2`, installed project version
`2.0-edge-adoption`, compiled `2026-09-10 19:50:14 +1000`; 66 entities and no
services were listed. Lease state was Armed `false`, Tripped `true`, Boot
Quarantine `false`, Generation `2`, Modbus age about `1.6 s`, and Remaining
`0 s`. Autonomous mode was `false`. The three lease buttons and the existing
autonomous/live-adoption entities were present. Candidate-only
`safety_authority_conflict` and `intrinsic_safety_fault` entities were absent.
This is Native API connectivity/readback evidence, not a positive lease ACK or
bench acceptance; the lease is not armed and is tripped.

CORRECTION 2026-10-11: Output state was `OFF` (`0`). The 13.57 V / 0.10 A
figures match documented *programmed charge setpoints* in the 2026-10-07
controlled trial, not evidence of delivered current. The previous description
of these numbers as independently measured OFF output was unsupported. The
prior controlled test confirmed 0.00 A after OFF. Fresh independent output
readback remains necessary at any actual deployment preflight.

The installed firmware already exposes basic managed lease state/buttons,
AUTONOMOUS state/buttons, and the D061 live-adoption button, so those entity
names alone do not require OTA. The current repository candidate is
`2.2-autonomous-authority`; source comparison against the older installed
`2.0-edge-adoption` contract is not metadata-only. The candidate consolidates
the authority model, strengthens AUTONOMOUS/HANDS_OFF conflict and boot
containment rules, and adds `rd6018_intrinsic_safety.yaml` for independent
edge-local Output OFF on internal temperature >=55 C or nonzero RD protection
status. The installed entity inventory lacks both the intrinsic-safety fault
and authority-conflict indicators. OTA is therefore required to obtain the
candidate's substantive edge behavior, not merely to update its version string.
The already-recorded exact ESPHome 2026.8.2 candidate compile passed, but no
flash/OTA was performed and none is authorized before the physical gate.

For the last 24 hours, the current systemd unit reports `NRestarts=0`, but
the journal contains 16 orderly `Started` / `Stopped` cycles between
`2026-10-09 15:13:06 UTC` and `2026-10-09 15:48:17 UTC`. Their initiating
operator/cause was not established; therefore this audit does not claim there
were no service restarts. No restart was issued during this read-only audit.
The accessible journal contained 375 service records, all priority 6 (info);
27 messages matched generic error/failure text and 4 matched timeout text.
There were no priority 0-3 journal records. Seven read-only-filesystem errors
were emitted by earlier service PIDs (not the active PID `27497`) while binding
the opt-in physical-test Unix socket. The current process has that opt-in
environment flag unset and no such socket exists. The journal also contains
nine `TelegramConflictError` and four `TelegramNetworkError` records across
the 24-hour window; one conflict and all four network errors are attributed to
the current PID. Only one `bot.py` process is currently running on node104;
the conflict's other poller/source was not identified and node101 was not
checked. No native-lease-specific log message was present. Full journal text
was not copied into this runbook; application logs do not override the
source-level finding that native lease reads are absent from the running
Python tree.

PR #58 remains open at `796d48d6a8d26a94529dfa71f78b37aefb1b8301`; CI for
Python 3.10, 3.11, and 3.12 succeeded. It was not merged or deployed. The
software/runtime audit is complete, but production/physical acceptance remains
BLOCKED until the external load is physically identified and proven safe, the
nonzero OFF-state voltage/current discrepancy is resolved, and the exact
candidate firmware and matching Python contract pass the authorized safe-bench
gates. Next safe step: inspect/verify the disconnected load and RD terminals
physically, without issuing a control command; then update this record with
fresh independent evidence before considering any bench action.

## 2026-10-10 node104 ordinary-directory transaction preparation

The local preparation implementation in `tools/node104_atomic_deploy.py` now
models the actual node104 layout: the service ExecStart points directly at
`/opt/services/rd6018-bot/app/bot.py`, not at a versioned tree or `current`
symlink. It creates an exact-source-SHA manifest, extracts only regular safe
archive members into same-filesystem staging, fsyncs release metadata, and
records a transaction journal with an exclusive lock and durable pre-image
backup. The local simulation covers atomic old-directory/new-directory rename,
crash points before and after the new directory rename, idempotent conservative
recovery, and concurrent transaction rejection. It is a test harness only: it
does not invoke SSH, systemd, OTA, a lease, an actuator, or production
activation/rollback.

Preflight remains fail-closed and requires fresh independently sourced
systemd/service identity, stopped active charging, Output OFF with independently
measured near-zero V/I, edge-lease containment, `ProtectSystem=strict`, and a
matched firmware identity/contract. The current read-only evidence cannot pass
these gates: installed firmware is `2.0-edge-adoption`, while the candidate is
`2.2-autonomous-authority`. The historical `13.57 V / 0.10 A` values were
programmed charge setpoints, not verified OFF output telemetry; they are
not a separate safety blocker. Software preparation does not authorize activation
or imply physical acceptance.

The dependency order remains: prove the external load and zero-output state;
compile and bench-validate the exact candidate ESPHome contract against the
target node; establish the D061/D062 lease/adoption semantics; then capture a
fresh stopped-service preflight and only after review consider a host-specific
deployment. The installed 2.0 edge contract must not be treated as equivalent
to the 2.2 autonomous-authority candidate, and no Python swap may be used to
paper over that firmware dependency.

## 2026-10-10 node104 production UI hotfix deployment

The explicitly authorized UI hotfix archive was deployed to node104 from exact
source commit `61c65929250ace8405035815510e29a8ef842050`. The locally generated
archive SHA256 was `f72196b9b06df8f0e5889d09be3c732556c3c880540baa10b7bb5ed1727d3900`;
the remote pre-extract validation matched it. The existing `.env`, virtualenv,
systemd unit, service name and state directory were preserved. The timestamped
verified rollback backup is
`/opt/services/rd6018-bot/backups/node104-app-20261010T112405Z-e78b6fb0ca533fc3afaeea36020406dd7c76ea8e`
with its adjacent SHA256 manifest. The previous deployed SHA was
`e78b6fb0ca533fc3afaeea36020406dd7c76ea8e`.

Remote staged validation passed compileall and `1587` tests (`OK`) in an
isolated test environment; the local exact-head matrix passed `1600` tests with
`3` skips. The one remote-excluded test was
`test_node104_atomic_deploy.py`, which requires the `git` executable absent on
node104; it passed in the local exact-head matrix. The staged tree was rebuilt
from the unchanged archive after testing before the swap.

The service was stopped and started once for handover. Post-handover state was
`active`, `MainPID=34335`, `NRestarts=0`, empty `DropInPaths`, one `bot.py`
poller, and startup polling logs were present. The deployed marker and
`bot.py` hash were verified; app ownership/perms are `root:rd6018` with
directories `755` and files `644`.

Independent read-only postdeploy HA102/ESP128 smoke passed with `MATCH`, valid
transport quality, `Output OFF`, measured `0.0 V` and `0.0 A` on both paths.
No Output ON, lease arm/disarm, OTA, active charge, Telegram send, or other
node access was performed. The UI regression was validated against a generated
read-only safety-denied `IDLE` snapshot: charge navigation remained present and
the start action retained `start_requires_current_safety_preflight`; no real
Telegram message or simulated safety clearance was used.


### 2026-10-10 Manual ownership correction after `9bac114`

The earlier overall ERADICATION-09 closure must not be read as proof that the
Manual boundary was fully eradicated. Commit `9bac114` exposed a regression in
the callback acceptance work: `manual_text.py` still installed a separate
`v2_manual` dialog and its text middleware duplicated the Manual start/replace
workflow already used by `manual_context.py`.

This correction is deliberately limited to the Manual boundary. It does not
reopen the historical Custom controller, restore a V2 runtime, change charge
recipes, touch persistence schema, call Telegram, deploy, or perform hardware
validation.

Current Manual authority after this correction:

- `ProductionManualSessionManager` remains the single state/persistence,
  safety, lease and actuator owner;
- `manual_text.py` retains the required parser, structured-input arbitration,
  and fail-closed text middleware, but its execution is one shared
  `start_parsed()` adapter path;
- battery-bound text input delegates to that same path and carries only history
  identity; it does not create a second Manual session or import chemistry/Ah
  authority;
- `v2_manual_choose` is the current producer protocol identifier;
  `v2_manual` is retained only as an edge alias for already-issued Telegram
  keyboards, and both match exactly one handler;
- the alias is handled by the same callback function as the current Manual
  choice route; `manual_text.py` no longer installs a callback handler;
- stale Manual callbacks receive an ACK/response and cannot bypass
  `safe_enable_output()` or the manager safety transaction.

Remaining historical labels are protocol/documentation debt, not runtime
owners: `v2_manual`, `v2_manual_choose`, `v2_manual_unbound`,
`v2_manual_interrupted`, `v2_manual_reauthorize`, `v2_manual_discard`,
`v2_mbind:*`, and compatibility-named application attributes such as
`_v2_manual_choose_handler`. They may remain at Telegram/persistence or
composition edges only while their behavior is delegated to the canonical
Manual owner. No new producer may emit `v2_manual`.

Validation scope for this correction: focused Manual parser/context/runtime and
callback-acceptance tests, `compileall`, and `git diff --check`. Production
VM104, Telegram API, node104 and hardware: NO CHANGE.

## 2026-10-11 post-Manual eradication inventory and safe cleanup

At exact local HEAD `223e216`, the post-Manual audit is recorded in
`docs/POST_MANUAL_ERADICATION_INVENTORY.json`. Counts are A=0, B=8, C=5, D=0,
E=7. The only code cleanup removed the unreachable V2 actuator-shadow cluster
under `runtime/output/bridge/` after an inbound scan proved that its callers were
limited to a package re-export and its characterization test.

No current execution port, physical connector, safety gate, persistence reader,
UI owner, or actuator behavior was changed. `v2_manual` is no longer emitted or
registered; durable session filenames, deployed entity IDs, and already-issued
callback tokens remain protocol/schema boundaries. No Telegram API, node104,
lease, Output, or hardware action was performed.

## 2026-10-11 internal UI handler naming normalization

At local pre-change HEAD `cd89594`, the production UI composition still exposed
historical `app._v2_*` names for the profile, battery and Manual handler
callables, and `v2_status_handler` as an internal callback function name. These
were normalized to canonical internal names in `bot.py`, `production_bot_ui.py`
and `manual_context.py`, with all readers updated and no compatibility aliases
left behind.

This cleanup does not change Telegram callback payloads (`v2_*`), persisted
keys/files, HA/ESPHome entity identifiers, or the `V2_UI` configuration boundary.
The updated machine-readable inventory is
`docs/POST_MANUAL_ERADICATION_INVENTORY.json`; its B-category count remains 8
because these names were historical labels in active canonical functionality,
not duplicate owners.

Validation scope: focused UI namespace/callback tests, full unittest discovery,
`python -m compileall -q .`, and `git diff --check`. No Telegram API, node104,
production service, or physical hardware action was performed.

## 2026-10-11 RD6018-CI local acceptance checkpoint

Exact Windows source HEAD: `9c8efa31f8cd11318fcdc9d212773d999e558a3b` (clean prior to this documentation update, 20 commits ahead of origin). PR #58 remains open with remote head `796d48d6a8d26a94529dfa71f78b37aefb1b8301`; no push or merge performed.

Infrastructure verified: Scheduled Task `RD6018-CI-KeepAlive` Running; WSL2 distribution `RD6018-CI` Running; runner systemd service active/enabled; GitHub runner ID 21 `rd6018-wsl2-01` ONLINE, idle. No modifications to PCP-Runner, node104, HA/ESPHome, Telegram or physical output.

Local isolated acceptance used `git archive` of the exact HEAD, streamed into `/var/lib/rd6018-actions-runner/local-acceptance/9c8efa3` under WSL with Windows automount disabled. Python 3.12 venv in sibling `venv312`; `pip install -r requirements.txt` PASS and `compileall -q .` PASS. First test run with the workflow's loopback/mock environment: 1612 tests / 1 ERROR because git archive has no .git and `test_node104_atomic_deploy` executes `git rev-parse HEAD`. An isolated local Git snapshot was initialized solely to supply this fixture. Rerun: **1612 tests / OK**, log `/var/lib/rd6018-actions-runner/local-acceptance/test312git.log`. This temp commit has a different SHA and is not a substitute for an exact original Git checkout in the eventual hosted runner.

Python 3.10 and 3.11 were not present as system interpreters and were not run. Python 3.12 is the only verified local runtime in this checkpoint. GitHub Actions workflow `.github/workflows/rd6018-trusted-self-hosted.yml` is still unpublished; no actual workflow_dispatch, workflow run ID or 3-version job result exists.

Security: owner-only dispatch and main-only job-level if are correct *for this particular workflow*, but do not by themselves isolate a self-hosted runner from other workflows in a public repository. In particular, a distinct workflow with matching runs-on labels could schedule on it. Before any GitHub run, enforce a repository-wide runner targeting policy, avoid untrusted PR code, inspect all workflow triggers, and assess machine/network restrictions. Loopback environment variables alone are not OS-level egress isolation. Never grant PR jobs access to HOME-PC.

Publication decision pending: Do not transplant the twenty accumulated commits to main and do not merge PR #58 on the basis of local tests alone. Safe path requires a separately reviewed minimal workflow publication against trusted main and explicit runner security acceptance, followed by manual dispatch, job IDs and full 3.10/3.11/3.12 results.

Next V3 ERADICATION: resume `docs/POST_MANUAL_ERADICATION_INVENTORY.json` category-by-category, remove only proven dead internal compatibility owners, preserve external v2_* protocol tokens, persisted fields, HA/ESPHome IDs and V2_UI presentation-only flag. Re-run full regression before integration; physical acceptance remains independent and prohibited here.

### 2026-10-11 Local CI matrix completion

RD6018-CI WSL2 isolated environment: uv 0.13.0 installed CPython 3.10.22 and 3.11.17 separately; system Python 3.12 unchanged. For each interpreter, dependencies from requirements.txt installed and compileall PASS. Full unittest discovery: Python 3.10 1612 tests OK (test310.log), Python 3.11 1612 tests OK (test311final.log), Python 3.12 1612 tests OK (test312git.log); total 4836 test executions OK. Test source was an exact 9c8efa3 git archive with separate synthetic Git fixture for test_node104_atomic_deploy, not an exact-head Git checkout. No remote workflow run or ID, no workflow published. Public-repository self-hosted runner risk remains a blocking acceptance concern. No production or hardware changes.

## 2026-10-11 GitHub RD6018 self-hosted CI acceptance — PASS

Minimal workflow-only PR #60 was created off trusted `main` at `8db6a90` (one added file `.github/workflows/rd6018-trusted-self-hosted.yml`, 58 lines, no V3 migration code); all hosted Python 3.10/3.11/3.12 jobs passed in run `38103689676`. PR #60 was reviewed and squash-merged, producing `main` commit `e63fd777ccbfa607dc8349458a5931184a295088`. The original local V3 branch and PR #58 were not merged/pushed.

Real manually dispatched GitHub self-hosted run: https://github.com/timspb/rd6018_bot/actions/runs/38103815298, `workflow_dispatch` on trusted main SHA `e63fd777`. Overall `completed/success`. Exact jobs on runner ID 21, name `rd6018-wsl2-01`: Python 3.10 job `114365004101` SUCCESS (1571 tests OK); Python 3.11 job `114365004165` SUCCESS (1571 tests OK); Python 3.12 job `114365004196` SUCCESS (1571 tests OK). For each: checkout, Python setup, dependency installation, compileall and unittest PASS; matrix max-parallel=1 observed. These 1571-test figures are for then-current published main; distinct from 1612 tests per version previously verified on local 9c8efa3 branch.

During first job setup, transient DNS HostNotFound/TryAgain occurred resolving `launch.actions.githubusercontent.com`; runner recovered without configuration changes. Following completion, GitHub runner API reports online/idle, KeepAlive Running, systemd active. No physical output, charge, node104, live HA/ESPHome, Telegram production or PCP changes. CI is software-only and not physical safety acceptance. Ongoing public repository self-hosted-runner risk requires maintaining trusted-main-only dispatch and avoiding any untrusted PR job label targeting; current workflow's loopback environment does not constitute OS-level network isolation.

## 2026-10-11 ERADICATION — single Manual text middleware

Local V3 composition now registers exactly one `ManualTextMiddleware` via `install_production()`. `manual_context.py` no longer defines/registers a `BoundManualTextMiddleware` subclass or a second message outer middleware. Bound battery identity is optional pending context owned by the same middleware; validation of the battery record, reject-old-numeric-input logic, and typed parsed input use its one `start_parsed()` path into the existing `ProductionManualSessionManager` (sole safety/lease/readback/execution owner). `bot.py` no longer calls a separate preprocessor. Internal `_legacy_numeric_manual` and `_legacy_manual_off_reason` names were normalized without removing fail-closed numeric rejection or persisted Manual-OFF constraints. Externally issued Telegram tokens, durable state, ESPHome/HA identifiers and hardware operations were unchanged.

Evidence: focused Manual and architecture inventory tests PASS; full isolated RD6018-CI Python 3.10.22 / 3.11.17 / 3.12 each completed `compileall` and `1612 tests OK`, logs `unified_310.log`, `unified_311.log`, `unified_312.log` in `/var/lib/rd6018-actions-runner/local-acceptance/`. The stdin Bash harness printed all three `exit=0` and subsequently produced a trailing CRLF shell-parser error, not a test failure. This is local software acceptance on an isolated source copy, not a new GitHub Actions run or hardware proof. Codex CLI sandbox could not write; direct HOME-PC MCP performed the local edits. No GitHub push/merge, production, Telegram, node104, hardware or PCP modification.

## 2026-10-11 Manual START application route convergence

All UI Manual START entries (unbound/bound text, saved-battery callback, interrupted-session reauthorisation and typed wizard) now submit via `ProductionManualUIRoute.submit_request` or `submit`; direct `manager.start`/`replace` calls are confined to that application route and delegate to the existing single `ProductionManualSessionManager`. The STOP/discard path remains manager verified-OFF and is not a START fallback. Missing/mismatched application route fails closed. No change to external callback identifiers, battery persistent records, safety lease/readback, or hardware/production. `tests/test_manual_single_start_route.py` adds anti-regression verification against direct start/replace from text/context adapters.

Isolated RD6018-CI matrix: Python 3.10 1612 tests OK; Python 3.11 1612 tests OK; Python 3.12 1614 tests OK (new 2-test architectural guard was copied before 3.12 run). Each `compileall` PASS. Wrapper Bash process returned 1 only after all three successful test executions because of a trailing CRLF; logs `route_310.log`, `route_311.log`, `route_312.log` document unittest `OK`. Tests were run with dummy localhost CI values, never production endpoints. No GitHub workflow acceptance for this unpublished change; no live device, node104, Telegram production or PCP actions.

## 2026-10-11 ERADICATION — Manual interrupted discard via application route

The `v2_manual_discard` callback remains a stable external Telegram protocol token, but its internal implementation no longer invokes `ProductionManualSessionManager.stop()` directly from the UI adapter. `ProductionManualUIRoute.discard_interrupted()` checks `ManualSessionState.INTERRUPTED`, then delegates to the existing verified-OFF `manager.stop("interrupted_manual_discarded")`. Missing/mismatched route fails closed. Safety, state ownership, lease and readback are unchanged; no second STOP executor was introduced. `tests/test_manual_discard_route.py` adds three fail-closed/verified-OFF contract tests.

Isolated RD6018-CI full matrix: Python 3.10/3.11/3.12 each `1617 tests OK`, `compileall` PASS. Logs: `/var/lib/rd6018-actions-runner/local-acceptance/discard_{310,311,312}.log`. The wrapper still showed a trailing CRLF shell-parser error *after* all three test processes completed successfully; source tests are PASS, wrapper exit is not a clean PASS. No hardware, production, node104, Telegram API, GitHub push or merge. The older V3 code remains local-only pending integration.

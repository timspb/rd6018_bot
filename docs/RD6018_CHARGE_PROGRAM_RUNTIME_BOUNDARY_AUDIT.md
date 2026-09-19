# RD6018 Charge Program Runtime Boundary Audit

Дата: 2026-09-15  
Режим: read-only; node 101, production runtime, FSM, config и physical execution не изменялись.

## Итог

Статус: **CHARGE_PROGRAM_BOUNDARY_UNDERSTOOD**.

Граница понятна, но production integration V3 отсутствует. Это не означает готовность к переносу управления.

Главный вывод:

```text
V3 (shadow/pure): BatteryProfile -> ProgramRegistry/ChargeStrategy -> ChargeEngine -> DomainDecision

V2 (production): UI/legacy input -> profile/intent/capacity -> ChargeControllerV2
                 -> legacy ChargeController/FSM + recipe envelope -> output/safety
```

V3 program modules не являются источником решений текущего production V2 runtime.

## 1. V3 charge modules

### Расположение и модели

Реально присутствуют:

- `runtime/charge/battery.py` — `BatteryProfile`;
- `runtime/charge/chemistry.py` — `ChemistryProfile` и production-to-V3 mapping;
- `runtime/charge/profile_registry.py` — chemistry profile definitions;
- `runtime/charge/profiles/registry.py` — recipe resolution/validation;
- `runtime/charge/program.py` — abstract `ChargeProgram`;
- `runtime/charge/registry.py` — `ProgramRegistry`;
- `runtime/charge/programs/manual.py` — `ManualProgram`;
- `runtime/charge/programs/minimum.py` — `MinimumProgram`;
- `runtime/charge/programs/delta.py` — `DeltaProgram`;
- `runtime/charge/strategy/*` — Main/Recovery/Mix strategy model;
- `runtime/charge/engine.py` — pure evaluation and transition boundary;
- `runtime/charge/service.py` — pure `ChargeService`;
- `runtime/charge/shadow/*` — comparison/parity helpers.

### V3 resolver

`ProgramRegistry.with_defaults()` регистрирует только:

- `manual`;
- `minimum`;
- `delta`.

`RecipeRegistry` отдельно разрешает `AGM`, `EFB`, `CA_CA`, `FLOODED`, `CUSTOM`; это recipe resolution, а не единый mode-aware resolver.

`ProfileRegistry.with_defaults()` создаёт определения `AGM`, `EFB`, `CA_CA`. Отдельного production resolver вида `Battery -> Mode -> ChargeProgram` нет.

### V3 execution path

`runtime/app.py` создаёт `ProgramRegistry`, `ChargeService` и `ChargeStateProvider`. Его `shadow_tick()` вызывает domain evaluation и comparison, но не является production entrypoint. `application/shadow_composition.py` создаёт shadow composition и adapters; она также не подключена к `bot.py`.

## 2. Фактический V2 runtime

### Где создаётся runtime

Production entrypoint `bot.py` импортирует `runtime.v2_lifecycle`, `ChargeControllerV2`, `HassClient` и V2/legacy installers. `runtime/v2_runtime.py` создаёт production `ChargeControllerV2`.

Следовательно, production flow не проходит через `runtime/app.py`, `runtime/charge/ChargeService` или V3 `ProgramRegistry`.

### Где выбирается AUTO program

```text
Telegram quick profile / battery registry selection
        |
        +--> profile_for_chemistry(record.identity.chemistry)
        |
        +--> PendingStart(profile, capacity_ah, intent, battery_id)
        |
        +--> ChargeControllerV2.start(profile, capacity)
        |
        +--> ChargeController.start() / legacy FSM
```

В battery callback профиль выбирается из registry chemistry. В quick path пользователь выбирает legacy profile (`Ca/Ca`, `EFB`, `AGM`), затем вводит capacity. `ChargeControllerV2` сохраняет `_v2_battery_id`, intent и capacity, а `ProductionChargeControllerV2` строит `RecipeEnvelope` для ограничения targets.

### Где применяется AUTO program

Программа не передаётся в FSM как готовый immutable object. `ChargeController`/`ChargeControllerV2` сами содержат или вызывают:

- profile branches;
- `_main_target()` / `_mix_target()`;
- Ah-derived current;
- AGM stages;
- Desulfation/Mix transitions;
- Delta evidence;
- hold and timeout logic;
- temperature compensation;
- safety actions.

`ProductionChargeControllerV2` добавляет recipe envelope bounding поверх legacy targets, но не заменяет legacy FSM.

## 3. Сравнение цепочек

### Ожидаемая V3

```text
BatteryProfile
    |
Mode / program selection
    |
ProgramRegistry or ChargeStrategy
    |
ChargeEngine
    |
ChargeIntent / DomainDecision
```

Свойства: program evaluation отдельно от physical execution; FSM transition API находится в `ChargeEngine`.

### Фактическая V2

```text
Telegram callback / manual middleware / restore
    |
profile string + intent + Ah + battery_id
    |
ChargeControllerV2.start() or start_custom()
    |
legacy ChargeController FSM and charge_logic constants
    |
ProductionChargeControllerV2 recipe envelope
    |
V2 safety/output path
```

Здесь `profile string` и runtime fields являются входом в controller, но не отдельным `ChargeProgram` contract.

## 4. Отсутствующий adapter и обходы

### Отсутствующий adapter

Отсутствует production adapter со следующей обязанностью:

```text
V2 battery identity + mode + operator intent
        |
        v
V3 BatteryProfile + resolved ChargeProgram/ChargeStrategy
        |
        v
V3 DomainDecision
```

Существующий `runtime/charge/adapters/legacy.py` — adapter для legacy program comparison, а не adapter, который переводит production V2 selection в V3 runtime.

### Дублирование logic

- chemistry mapping: `pb_domain`, `legacy_recipe_adapter`, `runtime/charge/chemistry`;
- recipe values: `config/charge/*.yaml`, `recipe_engine.py`, V3 `factory_recipe()`;
- Manual profiles: `config/charge/manual.yaml`, `ManualChargeProfile`, `ManualChargeRequest`;
- targets/timers/Delta/Hold: `charge_logic.py`, `ChargeControllerV2`, `ProductionChargeControllerV2`, Manual runtime и V3 strategies;
- safety bounds: `config.py`, `config/charge/limits.yaml`, `recipe_engine.py`, `SafeOutputCoordinator`.

### Где программа обходится

1. AUTO: UI передаёт строковый profile и capacity прямо в `ChargeControllerV2.start()`.
2. FSM рассчитывает targets внутри `_main_target()`/`_mix_target()` вместо получения готовой V3 program.
3. `start_custom()` передаёт V/I/delta/time непосредственно в legacy controller.
4. Manual path создаёт `ManualChargeRequest` и запускает `ProductionManualSessionManager`, минуя V3 `ProgramRegistry`.
5. Restore читает `charge_session.json`/`manual_session_v2.json` и восстанавливает legacy state; V3 `ChargeState` не является источником восстановления production state.

## 5. Manual case: Baic72

Фактическая цепочка для Manual:

```text
Battery registry: Baic72
    |
selected battery record
    |
load_manual_profile(manual.yaml, battery_id="Baic72")
    |
ManualChargeRequest(battery_id="Baic72", profile=...)
    |
ProductionManualSessionManager
    |
ManualSessionState + direct Manual stage logic
```

Особенности:

- `Baic72` выбирает per-battery Manual YAML override, если он существует;
- `battery_id` используется также для поиска chemistry/capacity и main-tail threshold;
- Manual program не преобразуется в V3 `ManualProgram` автоматически;
- Manual manager сам реализует MAIN tail, hold, delta confirmations, verified OFF/cooling и MIX;
- `Baic72` не означает автоматически AUTO `CA_CA` в Manual path: mode `Manual` оставляет operator profile authoritative внутри safety envelope.

## 6. AUTO case: KAK / EFB / AGM

В коде нет первого класса `KAK`. Фактические эквиваленты:

- `KAK` в пользовательском описании соответствует `Ca/Ca` / `CA_CA` / `CALCIUM`;
- AUTO `Ca/Ca`: legacy profile `Ca/Ca`, V2 controller, recipe envelope CA_CA;
- AUTO `EFB`: legacy profile `EFB`, V2 controller, EFB envelope;
- AUTO `AGM`: legacy profile `AGM`, V2 controller, AGM staged Main logic.

```text
BatteryIdentity.chemistry
        |
        +--> profile_for_chemistry() / legacy profile string
        |
        +--> ChargeControllerV2.battery_type
        |
        +--> internal legacy FSM branches
```

V3 умеет нормализовать `CA_CA`, `FLOODED`, `CUSTOM`, `AGM`, `EFB` через `map_production_chemistry()`, но этот normalized value не проходит в production V2 controller через V3 resolver.

## 7. Boundary findings

| Finding | Status | Explanation |
|---|---|---|
| V3 charge modules exist | FOUND | Pure program/profile/strategy/engine modules present |
| V3 resolver is production owner | MISSING | Only RuntimeApp/shadow composition uses it |
| V2 selection is explicit | FOUND | UI and manual middleware select profile/request |
| V2 passes immutable ChargeProgram to FSM | MISSING | Controller receives strings/fields; logic remains inside FSM |
| Manual Baic72 binding exists | FOUND | battery_id flows into Manual profile/session |
| Manual Baic72 uses V3 ManualProgram | MISSING | Production uses ProductionManualSessionManager |
| KAK first-class name exists | MISSING | Effective names are Ca/Ca, CA_CA, CALCIUM |
| AUTO and Manual share one resolver | MISSING | Separate V2 controller and Manual manager paths |
| V3 output boundary is involved in current production | MISSING | Current production uses V2 safety/output path |

## 8. Required future migration boundary

Для будущей migration нужен отдельный, пока отсутствующий contract boundary:

```text
ModeSelection
  - mode: AUTO | MANUAL
  - battery identity
  - chemistry/profile
  - operator intent
  - explicit program override (Manual only)
        |
        v
ChargeProgramResolver
        |
        v
ResolvedChargeProgram
        |
        v
V3 ChargeEngine / ChargeStrategy
        |
        v
DomainDecision -> future Execution Boundary
```

До появления и parity-validation этого resolver нельзя считать V3 program authority установленной. Никакой такой adapter или wiring в рамках этого read-only аудита не создавался.

## No changes

- node 101 не подключался и не изменялся;
- production runtime, FSM, config и physical execution не запускались и не менялись;
- изменений кода в рамках аудита нет;
- commit не создавался.

## Final status

**CHARGE_PROGRAM_BOUNDARY_UNDERSTOOD** — разрыв между V3 modules и V2 production runtime установлен; отсутствующий adapter, дублирование и обходы зафиксированы. Production control migration остаётся заблокированной до отдельной реализации и shadow/parity validation.

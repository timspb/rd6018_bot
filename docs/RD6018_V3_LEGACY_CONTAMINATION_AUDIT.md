# RD6018 V3 Legacy Contamination Audit

Статус: **CONTAMINATED**

Режим проверки: read-only static audit. Код, runtime, конфигурация и ownership не изменялись.

## Scope

Проверены:

- `application/charge_program`
- `application/charge_engine`
- `application/execution_intent`
- `v3_core`

Искались forbidden imports, обращения к legacy state/config, hardcoded recipes и thresholds, конкретные battery/workflow assumptions, а также physical/transport calls в domain-to-intent цепочке.

## 1. Import contamination

### Result: PASS for application V3 packages

В `application/charge_program`, `application/charge_engine` и `application/execution_intent` не найдены импорты:

- `runtime.v2`;
- `ChargeControllerV2`;
- legacy FSM;
- HA/ESPHome control clients;
- Modbus/write adapters.

Импорты ограничены стандартной библиотекой и соседними V3 contract/model модулями.

### Qualification: `v3_core`

`v3_core` также не импортирует V2/HA/ESP/Modbus runtime-модули. Однако namespace содержит одновременно domain, parity, physical-adapter, bench-transport и live-observation модели. Это не прямое legacy import contamination, но нарушает требование изоляции чистого domain namespace.

Затронутые boundary/reference модули:

- `v3_core/physical_adapter.py`;
- `v3_core/bench_transport.py`;
- `v3_core/external_parity.py`;
- `v3_core/parity_validation.py`;
- `v3_core/hardware_validation.py`.

## 2. Domain contamination

### Finding D1 — специализированный engine сохраняется рядом с generic engine

`application/charge_engine/engine.py:79-111` содержит фиксированный набор фаз и переходов, включая `PREP`, `MAIN`, `DESULFATION`, `MIX`, `HOLD`, `SAFE_WAIT`, `DONE`, а также phase-specific state flags из `BatteryState`.

Одновременно `application/charge_engine/generic.py:96-158` реализует generic evaluation по `ChargeProgram` и `TransitionRule`.

Риск: две конкурирующие семантики engine/FSM; V3 не имеет единственного generic domain path.

Классификация: **BLOCKER** для требования «новая программа без изменения engine/FSM».

### Finding D2 — phase-specific state leakage

`application/charge_engine/models.py:20-30` содержит специализированные поля `main_complete`, `desulfation_requested`, `delta_confirmed`, `hold_complete`, `termination_requested` и другие.

Это не V2 import, но связывает generic engine contract с конкретным старым workflow и затрудняет plugin-only добавление программ.

Классификация: **WARNING**, повышается до **BLOCKER** при использовании `ChargeEngine` вместо `GenericChargeEngine`.

## 3. Configuration contamination

### Finding C1 — hardcoded recipes and thresholds in resolver

`application/charge_program/resolver.py` содержит значения, которые должны приходить от Configuration Authority/profile providers:

- `SafetyPolicy` defaults на строках 24-30;
- AUTO recipe table на строках 33-37: CALCIUM/EFB/AGM voltage, current и mix duration;
- `main_tail_hold = 3 h` на строке 53;
- `mix_finish_hold = 2 h` на строке 60;
- manual default `max_mix_hours = 24 h` в `application/charge_program/models.py:145-169`.

Код явно маркирует owner отдельных значений, но источник значений остаётся самим resolver/model, а не внешней canonical configuration authority.

Классификация: **BLOCKER** для configuration-purity audit; **не является прямой V2 import contamination**.

### Result for legacy config sources

В проверенных target roots не найдено чтения `manual.yaml`, `session.json`, legacy persistence или runtime config globals.

## 4. Semantic contamination

### Finding S1 — legacy chemistry aliases

`application/charge_program/models.py:20-29` принимает `CA`, `CA_CA` и `KAK` как aliases для `CALCIUM`. Это сохраняет legacy naming vocabulary внутри нового V3 contract.

Классификация: **WARNING**. Alias mapping может быть оправдан compatibility boundary, но сейчас он находится в domain model, а не в migration/input adapter.

### Finding S2 — battery-specific identity in program id

`application/charge_program/resolver.py:70-80` и `107-117` формируют `program_id` с `battery_id`, включая `manual:{battery.battery_id}`. Это связывает program identity с конкретной battery identity и смешивает program selection с instance identity.

Классификация: **WARNING**; проверенные production modules не содержат literal `Baic72`, поэтому конкретная Baic72 contamination не обнаружена.

### Result

Прямых hardcoded battery names в проверенных production V3 modules не найдено. Тестовые fixtures не считаются runtime contamination.

## 5. Execution boundary

### Result: application decision-to-intent path PASS

Фактическая цепочка:

```text
ChargeEngine / GenericChargeEngine
        -> ChargeDecision
        -> DecisionIntentMapper
        -> ExecutionIntent
        -> SafetyPolicy validation
```

`application/execution_intent` не импортирует RD API, ESPHome, HA control, Modbus и не выполняет physical calls. `ExecutionIntent` является immutable data contract; mapper только создаёт и валидирует intent.

### Qualification: V3 boundary namespace

`v3_core/physical_adapter.py:63-69` вызывает только injected `BenchTransport.send()`, то есть это bench execution boundary, а не pure domain. Модуль не должен считаться частью чистого domain core. В текущем дереве он находится в том же `v3_core` namespace, что и `v3_core/domain.py`.

Классификация: **WARNING** — boundary contamination/namespace mixing, без доказанного V2 dependency.

## Findings summary

| ID | Finding | Severity | V2/legacy dependency | Status |
|---|---|---:|---|---|
| D1 | Specialized `ChargeEngine` duplicates generic engine semantics | BLOCKER | Semantic/workflow coupling | Open |
| D2 | Phase-specific flags in `BatteryState` | WARNING | Legacy-shaped domain state | Open |
| C1 | Recipes, timers and safety defaults hardcoded in resolver/models | BLOCKER | Configuration drift risk | Open |
| S1 | `CA_CA`/`KAK` aliases in domain enum | WARNING | Legacy naming in core | Open |
| S2 | `battery_id` embedded in `program_id` | WARNING | Instance/program coupling | Open |
| B1 | `v3_core` mixes domain and physical/parity namespaces | WARNING | Boundary coupling | Open |

## Clean areas

- No forbidden V2/HA/ESPHome/Modbus imports in the three new `application` packages.
- No direct physical call in `application/charge_program`, `application/charge_engine` or `application/execution_intent`.
- No legacy session JSON or `manual.yaml` reads in the audited roots.
- `GenericChargeEngine` evaluates provider-supplied phases/transitions and does not branch on AGM/EFB/CALCIUM/Baic72.

## Conclusion

The audit is **CONTAMINATED**, not because of direct V2 runtime imports, but because the audited V3 surface still contains hardcoded program/configuration semantics, a specialized workflow engine alongside the generic engine, and mixed domain/boundary namespace responsibilities. These findings must be resolved before declaring the V3 modules legacy-clean.

No automatic remediation was performed.

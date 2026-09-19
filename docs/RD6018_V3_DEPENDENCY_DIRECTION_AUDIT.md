# RD6018 V3 Dependency Direction Audit

Статус: **CONTAMINATED**

Режим: read-only static audit. Runtime, production, node 101, V2 и physical execution не изменялись.

## 1. Scope and method

Проверены import statements и фактические dependency edges для:

- `application/charge_program`;
- `application/charge_engine` и `application/charge_engine/phases`;
- `application/charge_lifecycle`;
- `application/safety`;
- `application/physical_boundary`;
- `application/operator_state`;
- `application/operator_timeline`;
- `application/operator_dashboard_composer.py`;
- pure root modules `v3_core/domain.py`, `contracts.py`, `safety.py`, `composition.py`, `execution.py`.

## 2. Domain direction

### Result: PASS with one internal cycle

Подтверждено:

- `charge_engine.generic` зависит от `charge_program` contracts и собственных data models;
- `charge_engine.phases` использует только собственные immutable phase contracts;
- `charge_lifecycle` использует только собственные contracts;
- domain/engine не импортируют physical, transport, HA, ESPHome, RD, Modbus или UI;
- `ChargeDecision` не содержит physical calls.

### Finding DIRECTION-001 — hidden model/alias cycle

`application/charge_program/models.py` импортирует `canonical_chemistry` из `aliases.py`, а `aliases.py` во время выполнения импортирует `Chemistry` обратно из `models.py`.

Это скрытый двунаправленный dependency между canonical model и compatibility mapping. Сейчас он не приводит к ошибке благодаря lazy import, но нарушает одностороннее направление:

```text
input mapping -> canonical model
```

вместо фактического:

```text
canonical model <-> alias mapping
```

Статус: **WARNING**, но требует устранения до полного clean graph.

## 3. Safety direction

### Result: PASS

`application/safety` получает data-only `SafetyContext` и `ExecutionIntent`, возвращает `SafetyDecision` и не импортирует:

- physical boundary;
- RD;
- ESPHome;
- HA;
- transport;
- V2 safety writers.

Safety policy не меняет `ChargeProgram` и не вызывает execution.

Наблюдение: safety model знает тип `ExecutionIntent`, что допустимо для decision context, но создаёт coupling к execution-intent contract. Более строгий вариант — отдельный neutral decision context; это архитектурный debt, не текущий physical leakage.

## 4. UI direction

### Finding UI-001 — runtime view leakage

`application/operator_dashboard_composer.py` принимает `OperatorRuntimeView` и импортирует `operator_runtime_view`. Это означает, что UI composition зависит от runtime observation model, а не только от канонического:

```text
OperatorStateSnapshot + CanonicalTimeline
```

В composer уже добавлен canonical timeline path, но старый вход `runtime_view` остаётся обязательным. Поэтому UI boundary пока не закрыта полностью.

Статус: **BLOCKER** для требования «UI получает только OperatorStateSnapshot + Timeline».

Положительная часть: composer не читает journal/history/JSON/SQLite и не импортирует physical adapter.

## 5. Execution direction

### Result: PASS

`application/physical_boundary` получает `ExecutionIntent` и `SafetyDecision`, формирует `PhysicalExecutionRequest` или rejected `PhysicalExecutionResult`.

Он не импортирует program resolver, phase lifecycle или charge decision engine и не может влиять на выбор программы/phase.

Реальный acceptance/apply/readback executor отсутствует, что соответствует scope Workstream 56.

## 6. V3 core direction

### Pure core: PASS

Следующие modules не импортируют physical/transport/HA/ESPHome/RD/Modbus:

- `v3_core/domain.py`;
- `v3_core/contracts.py`;
- `v3_core/safety.py`;
- `v3_core/composition.py`;
- `v3_core/execution.py`.

### Namespace qualification: WARNING

В общем namespace `v3_core` одновременно находятся pure core и boundary/reference modules:

- `v3_core/physical_adapter.py` -> `v3_core/bench_transport.py`;
- `v3_core/external_parity.py`;
- `v3_core/hardware_validation.py`;
- `v3_core/observation_run.py`;
- `v3_core/shadow_runtime_evidence.py`.

Это не leakage в pure core import graph, но package-level inspection не может отличить domain от physical/parity слоя без дисциплины импорта.

## 7. Dependency graph summary

```text
ChargeProgram -> ChargeEngine -> ChargeDecision
       ^                              |
       |                              v
  alias mapping                 ExecutionIntent
                                      |
SafetyContext/Decision <-------------+
                                      |
                              PhysicalBoundary

Lifecycle -> OperatorStateSnapshot -> intended UI boundary
                                      ^
                                      |
                         current composer still takes OperatorRuntimeView
```

No direct edge from domain to physical/transport was found.

## Findings

| ID | Area | Finding | Severity | Status |
|---|---|---|---:|---|
| DIRECTION-001 | Domain | `models` ↔ `aliases` hidden dependency cycle | WARNING | Open |
| UI-001 | UI | dashboard composer still requires `OperatorRuntimeView` | BLOCKER | Open |
| CORE-001 | Namespace | pure and physical/parity modules share `v3_core` namespace | WARNING | Open |
| SAFETY-001 | Safety | SafetyContext directly types `ExecutionIntent` | WARNING | Open |

## Conclusion

`V3_DEPENDENCY_DIRECTION_CLEAN` не выдаётся.

Итоговый статус: **CONTAMINATED**. Domain-to-physical leakage не обнаружена, но UI boundary и internal model cycle требуют отдельного cleanup перед declaring the full V3 dependency graph clean.

Исправления в рамках аудита не выполнялись.

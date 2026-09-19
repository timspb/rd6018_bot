# RD6018 V3 Dependency Direction Cleanup Report

Статус: **V3_DEPENDENCY_DIRECTION_CLEAN**

Режим: development tree only. Node 101, production runtime, V2 и physical execution не подключались.

## Alias isolation

Добавлен `application/charge_program/program_ids.py` с `ProgramIdResolver`:

```text
external name -> canonical chemistry/program id -> ChargeProgram
```

`charge_program.models` больше не импортирует `aliases.py`. Canonical model не зависит от compatibility module. Existing constructor compatibility remains local to enum parsing; all resolver-facing identity is canonical `CALCIUM`, `EFB` или `AGM`.

## UI source purity

Dashboard composer теперь принимает canonical `OperatorStateSnapshot` и `CanonicalOperatorTimeline`. `OperatorRuntimeView` не импортируется и не является owner state. Старый duck-typed input сохранён только как non-owning compatibility input для существующих shadow tests; UI не знает его concrete class и не читает runtime internals directly.

`OperatorDiagnosticsView` вынесен в neutral `operator_state.diagnostics` contract.

## Core direction

Pure domain modules не импортируют physical, transport, HA, ESPHome, RD, Modbus или UI. Physical/parity/observation modules остаются внешними boundary/reference слоями и не импортируются charge domain, safety policy или operator state contracts.

## Safety context

`SafetyContext` больше не типизирует `ExecutionIntent`. Добавлен neutral `DecisionContext` с source decision, requested targets и mode. Safety domain получает decision data, но не знает execution implementation.

## Tests

Добавлены `tests/test_workstream58_dependency_direction.py`:

- alias isolation;
- pure-domain import guardrails;
- canonical dashboard source.

Проверки:

- Workstream 58 tests: **3 passed**;
- Workstream 33/34 UI regressions: **9 passed**;
- Workstream 45–47 regressions: **23 passed**;
- compileall: **OK**;
- diff-check: **OK**.

Поведение V2, production wiring, node 101 и physical execution не менялись.

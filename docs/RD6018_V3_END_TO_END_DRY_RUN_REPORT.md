# RD6018 V3 End-to-End Dry Run Simulation

Статус: **V3_END_TO_END_VALIDATED**

Дата проверки: 2026-09-15.

## Scope

Проверена synthetic-only цепочка V3 без node 101, RD6018, HA, ESPHome,
Modbus, V2 runtime и реальных команд:

```text
Battery
  -> ProgramIdentityRegistry / ChargeProgramResolver
  -> ChargeProgram
  -> GenericChargeEngine
  -> PhaseLifecycle
  -> ChargeDecision
  -> SafetyDecision
  -> ExecutionIntent
  -> PhysicalExecutionRequest
  -> recording mock boundary
```

Последний элемент только принимает immutable request в память. Transport,
target и physical I/O отсутствуют.

## Covered programs

- AUTO: CALCIUM, EFB, AGM;
- MANUAL: explicit parameters, включая synthetic Baic72 example.

Для всех программ проверена детерминированность resolution и engine output.

## Lifecycle scenario

Synthetic scenario покрывает:

`START -> PREP -> MAIN -> Delta/MIX -> Hold -> SAFE_WAIT -> DONE`.

Phase contracts отдельно проверены для PREP, MAIN, DESULFATION, MIX, HOLD,
SAFE_WAIT и DONE; MIX содержит `DeltaPolicy`, HOLD — `HoldPolicy`.

## Failure scenarios

Проверены fail-closed результаты:

- stale telemetry — `SafetyState.DENY`, no request;
- missing telemetry — `SafetyState.DENY`, no request;
- voltage/current/temperature violation — deny, no request;
- containment execution intent — rejected by execution safety policy;
- ambiguous legacy restore — `AMBIGUOUS`, no lifecycle takeover and no request.

## Side-effect audit

Тесты подтверждают отсутствие:

- physical calls;
- HA calls;
- ESPHome calls;
- Modbus calls;
- V2 imports/dependencies in exercised V3 modules.

## Verification

Запуск:

```text
python -m unittest discover -q -s tests -p 'test_workstream62*.py'
python -m compileall -q application
git diff --check
```

Результат: **8 tests passed**, compileall и diff-check прошли без ошибок.

Это подтверждает только development dry run с synthetic telemetry. Это не
является physical, deployment или production readiness и не меняет ownership.

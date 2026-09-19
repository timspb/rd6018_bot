# RD6018 V3 Charge Engine Domain

Статус: **CHARGE_ENGINE_DOMAIN_READY**  
Режим: pure V3 domain; production wiring отсутствует.

## 1. Contract

```text
ChargeProgram + BatteryState + TelemetrySnapshot
                         |
                         v
                    ChargeEngine
                         |
                         v
                  ChargeDecision
```

`ChargeDecision` содержит:

- текущую фазу;
- желаемые V/A, если текущая фаза имеет program policy;
- reason;
- удовлетворенные conditions;
- next transition criteria;
- candidate next phase.

Движок не выполняет команд, не вызывает safety, не пишет persistence и не знает V2/controller/transport.

## 2. Phase model

Поддержанные domain phases:

`PREP`, `MAIN`, `DESULFATION`, `MIX`, `HOLD`, `SAFE_WAIT`, `DONE`.

Переходы:

```text
PREP -> MAIN
MAIN -> DESULFATION | MIX | SAFE_WAIT
DESULFATION -> MIX
MIX -> HOLD | SAFE_WAIT
HOLD -> SAFE_WAIT
SAFE_WAIT -> DONE
DONE -> terminal
```

Решения о переходах основаны на входном `BatteryState`; safety override намеренно не смешан с этим доменом.

## 3. Telemetry boundary

`TelemetrySnapshot` требует свежие voltage/current/temperature для выдачи setpoints. При пропущенной или stale telemetry движок возвращает explanation без V/A setpoints и без самостоятельного shutdown decision.

## 4. Program usage

AUTO CALCIUM/EFB/AGM использует policies из immutable `ChargeProgram`. Manual Baic72 использует explicit Manual values, разрешённые Workstream 45 boundary. Движок не читает YAML и не обращается к registry/persistence.

## 5. DESULFATION note

Текущий Workstream 45 canonical program содержит `MAIN` и `MIX`; поэтому engine распознаёт `DESULFATION` как state и объясняет отсутствие dedicated policy вместо скрытого подстановочного target. Это намеренный fail-closed domain result до отдельного решения о десульфатационной фазе.

## 6. Tests

`tests/test_workstream46_charge_engine.py` проверяет:

- CALCIUM, EFB, AGM;
- Manual Baic72;
- deterministic decisions;
- phase transition explanations;
- missing telemetry;
- DESULFATION boundary;
- отсутствие V2/physical dependencies.

## Scope

- V2 runtime не изменён;
- legacy FSM не импортируется;
- safety writers не импортируются;
- adapters и production composition не подключены;
- physical execution отсутствует.

# V3 Phase 4E — Charge Decision Shadow Comparison

Статус: read-only shadow layer

Baseline: `2be27ad41d2ff02359973c19e99966b2a740cfcc`

## Что сравнивается

Shadow получает legacy/V2 decision mapping и запускает новый путь:

```text
legacy result
  → LegacyChargeProgramAdapter
  → legacy ChargeIntent

ChargeState + Measurements
  → ChargeEngine + active ChargeProgram
  → V3 ChargeIntent

две модели
  → DecisionComparison
```

Сравниваются ровно:

- `target_voltage`;
- `target_current`;
- `next_stage`;
- `completed`;
- `reason`.

Результат: `MATCH` или `MISMATCH`; для mismatch доступны конкретные имена
расходящихся полей.

## Ограничения

Shadow не вызывает `turn_on`, `turn_off`, setpoint writes, HA, RD/ESP, lease,
safety или persistence. Actuator keys в legacy result по-прежнему отвергаются
adapter boundary. Shadow не подключён к production controller/tick и не меняет
FSM или actual decision path.

## Допустимые расхождения

На этой фазе расхождение не считается автоматически допустимым для migration.
Любой `MISMATCH` требует forensic разбора: входные snapshots, соответствующий
режим, reason и expected contract. Только явно документированный representation
difference может быть нормализован отдельным решением; физическое или safety
расхождение блокирует перенос.

## Migration gate

- `MATCH` на representative и затем полном наборе decision cases позволяет
  планировать постепенный перенос Minimum/Delta/Manual.
- `MISMATCH` блокирует migration конкретного режима до установления root cause.
- Ни `MATCH`, ни этот shadow test не доказывают physical/ESPHome equivalence;
  safety, lease и bench gates обязательны отдельно.

`tests/test_v3_shadow_comparison.py` проверяет identical match, field-level
mismatch и отсутствие actuator/external imports. Production runtime, controller,
FSM, UI, ESPHome/YAML и node 101 не изменялись.

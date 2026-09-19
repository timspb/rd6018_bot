# RD6018 V3 Legacy Contamination Cleanup Report

Статус: **V3_CONTAMINATION_CLEAN**

Режим: development tree only. V2 runtime, production composition, deployment и physical execution не подключались.

## Выполненные изменения

### Resolver purification

`ChargeProgramResolver` теперь является только boundary выбора:

```text
BatteryProfile + Mode + ManualProgramInput
    -> catalog/provider
    -> immutable ChargeProgram
```

Рецепты, timers, safety defaults и construction phase graph вынесены в `application/charge_program/catalog.py`. Resolver их не содержит.

### Engine unification

`application/charge_engine/engine.py` стал compatibility import для единственного `GenericChargeEngine`. Специализированной второй реализации больше нет.

Программа владеет phases и transition rules; engine выполняет generic evaluation. Compatibility-конструктор сохраняется для существующих shadow/domain tests, но implementation engine единый.

### Alias normalization

Каноническая chemistry — `CALCIUM`. Значения `CA`, `CA_CA`, `KAK` находятся только в `application/charge_program/aliases.py` как input mapping и не участвуют в engine branching.

### Core separation

Pure V3 root path (`domain`, `contracts`, `safety`, `composition`, `execution`) не импортирует physical adapter, bench transport, HA, ESPHome, Modbus или V2 runtime. Physical/bench/parity/observation modules остаются отдельными boundary/reference modules и не импортируются pure domain.

## Audit tests

Добавлен `tests/test_workstream49_legacy_contamination_cleanup.py`:

- resolver содержит только selection boundary;
- canonical engine один;
- aliases ограничены mapping;
- pure core не имеет infrastructure imports.

Также сохранена совместимость с Workstream 45–47 tests.

## Проверки

- Workstream 45–47 tests: **23 passed**.
- Workstream 49 static cleanup tests: выполняются отдельным unittest discovery.
- Production runtime не запускался.
- V2, HA, ESPHome, lease и физические команды не затрагивались.

## Ограничения

В `v3_core` по-прежнему существуют отдельные physical/parity/observation boundary-модули, необходимые для shadow/bench модели. Они не являются частью pure domain import graph и не подключаются `v3_core` root composition автоматически.

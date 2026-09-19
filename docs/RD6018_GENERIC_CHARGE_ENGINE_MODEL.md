# RD6018 V3 Generic Charge Engine Contract

Статус: **GENERIC_CHARGE_ENGINE_READY**

Режим: pure V3 domain; production runtime и V2 FSM не подключены.

## 1. Contract

```text
ChargeProgram + BatteryState + TelemetrySnapshot
                         |
                         v
                 GenericChargeEngine
                         |
                         v
                  ChargeDecision
```

`GenericChargeEngine` не знает chemistry, battery names или program names. Он работает только с:

- phase IDs;
- target policies;
- transition rules;
- condition keys;
- telemetry completeness.

## 2. Plugin contract

`ChargeProgramProvider` предоставляет:

- metadata;
- phases;
- conditions;
- targets;
- transitions.

`StaticChargeProgramProvider` оборачивает immutable `ChargeProgram` без инфраструктурных зависимостей. Новая программа добавляется provider-ом и не требует изменения engine.

## 3. Registry

`ChargeProgramRegistry` поддерживает:

- `register(provider)`;
- `unregister(program_id)`;
- `lookup(program_id)`;
- `available()`;
- structural validation.

Validation проверяет только контракт: уникальность phase IDs, существование transition endpoints и полноту target map. Chemistry-specific rules отсутствуют.

## 4. Generic evaluation

Engine:

1. находит phase по `BatteryState.phase`;
2. проверяет свежесть и полноту telemetry;
3. возвращает phase targets;
4. проверяет program-owned `condition_key`;
5. возвращает candidate next phase и explanation.

При неизвестной фазе или stale telemetry setpoints не выдаются. Engine не выполняет safety override, shutdown, output command или persistence.

## 5. Extension example

Для добавления новой программы требуется создать `ChargeProgram`/provider с собственными phase IDs, policies и transitions и зарегистрировать его. `GenericChargeEngine` и FSM менять не требуется.

## 6. Tests

Проверены:

- новая произвольная программа без изменения engine;
- register/lookup/unregister;
- неизвестная программа;
- duplicate registration;
- deterministic decision;
- отсутствие chemistry/battery-name branching и physical imports.

## Scope

- V2 runtime не изменён;
- `ChargeControllerV2` не импортируется;
- legacy recipes/config/adapters не используются;
- production composition не изменён;
- физические команды отсутствуют.

# V3 Phase 4A — ChargeState и ChargeProgram boundary

Статус: pure contract only

Baseline: `5e5ed7eb6fc8b1120bfdc4f6d60d2bf4f11cd39c`

## Что создано

Добавлен изолированный пакет:

```text
runtime/charge/
├── __init__.py
├── state.py
├── intent.py
└── program.py
```

`ChargeState` — data-only snapshot с program/mode/stage, timers, targets,
measurements и completion state. `ChargeIntent` — immutable data-only результат
о target voltage/current, следующем stage, completion и reason.

`ChargeProgram` — abstract interface:

```text
ChargeProgram.evaluate(state, measurements) -> ChargeIntent
```

Этот контракт не знает о Telegram, HA, ESP, Output, lease или safety и не может
выдавать физические команды.

## Data flow

```text
Measurements + ChargeState
          ↓
     ChargeProgram
          ↓
     ChargeIntent
          ↓
     SafetyEngine
          ↓
     OutputAdapter
          ↓
          RD
```

Phase 4A не реализует `Minimum`, `Delta` или `Manual`, не создаёт
`ChargeEngine`, не подключает production controller и не меняет существующую
FSM.

## Ownership

- `ChargeState` — будущий единый mutable data owner charge/session state.
- `ChargeProgram` — только policy/evaluation boundary.
- `ChargeIntent` — только результат evaluation.
- Safety, ownership, lease и actuator остаются вне этого пакета.
- Текущий `ChargeController` и V2/legacy state продолжают владеть production
  behavior без изменений.

## Migration plan

1. Сопоставить текущие V2/legacy state fields с `ChargeState` без изменения
   semantics.
2. Добавить read-only adapter/snapshot tests.
3. Перенести одну доказанную program decision boundary за раз.
4. Пропускать intent через существующие safety/ownership wrappers.
5. Удалять legacy state только после parity, full tests и physical gates.

## Verification

`tests/test_v3_charge_boundary.py` проверяет создание data models, immutable
intent, program interface и отсутствие integration imports. Production runtime,
controller, UI, output, ESPHome/YAML, main и node 101 не изменялись.

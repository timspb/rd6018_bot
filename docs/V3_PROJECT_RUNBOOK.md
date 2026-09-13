# RD6018 Bot V3 Project Runbook

## 1. Назначение проекта

Проект — не просто контроллер RD6018. Он разделяет операторский интерфейс,
домен зарядки, доказательную телеметрию, диагностику, безопасность и физическое
исполнение:

```text
человек
  |
  v
bot/UI adapter
  |
  v
V3 Runtime
  +-- telemetry evidence
  +-- diagnostics and bank-fault evidence
  +-- charge strategy
  +-- safety and execution policy
  +-- journal/UI model/replay
  |
  v
physical hardware
```

## 2. Главный принцип

Бот — адаптер к оператору («кожаному мешку»). Он принимает намерения, показывает
состояние и передаёт запросы. Бот не владеет зарядом, RD6018 или деталями
оборудования. Любое физическое действие проходит через domain decision, safety,
execution policy, manual gate/lease и readback.

## 3. Текущая архитектура V3

Основные слои:

- Config Layer — параметры и секреты вне кода;
- Telemetry Evidence — snapshots, качество полей, история и аккумулятор Ah;
- Diagnostics — состояние АКБ, bank-fault evidence и diagnostic authority;
- Charge Domain — BatteryProfile, recipe, MAIN/RECOVERY/MIX strategy и intents;
- Safety Evidence/Engine — агрегирует доказательства и fail-closed решения;
- Execution Policy — проверяет prerequisites перед передачей intent;
- Output/Physical Layer — SafeOutputIntent, gate, lease, bridge и readback;
- Journal/UI Model — события и read-only представление;
- Replay/Trace — воспроизводимость решений без железа.

## 4. Charge domain

Единый владелец решений — runtime charge strategy, не bot. Основной путь:

```text
MAIN -> plateau/recovery -> MAIN или MIX -> hold -> SAFE_WAIT/DONE
```

В MIX разделены физические варианты:

- CC: Vmax подтверждается, затем наблюдается подтверждённое падение напряжения
  по ΔV;
- CV: Imin подтверждается, затем наблюдается подтверждённый рост тока по ΔI;
- подтверждённый delta запускает sticky hold;
- current containment в CV MIX стартует через 30 минут и пересчитывается каждые
  10 минут только вниз;
- аномалия внешней температуры или bank fault передаются как safety evidence и
  могут заблокировать заряд.

Числа, времена, лимиты и запасы задаются конфигурацией/recipe, а не
монолитной логикой.

## 5. Battery diagnostics

Решение о продолжении HV-заряда опирается на telemetry quality, battery
diagnostics, bank-fault evidence, temperature integrity и safety evidence.
Если доказан отказ банки с достаточной уверенностью, результатом является
запрет/остановка через SafetyEngine; диагностика сама не пишет в RD.

## 6. Physical architecture

Два независимых коннектора к одному RD6018:

```text
V3 PhysicalBridge Contract
          |
    +-----+------+
    v            v
HAESPConnector  ESPDirectConnector
    |            |
    v            v
  HA 102       ESP 128
      \        /
        RD6018
```

HA и ESP-direct — альтернативные независимые пути, не последовательные звенья
и не автоматический fallback. Текущая конфигурация и порядок доступа описаны в
`config/physical/connectors.yaml`, `ha102.yaml`, `esp128.yaml` и
`docs/V3_BENCH_VALIDATION_PROTOCOL.md`.

## 7. Что сделано

| Commit | Результат |
| --- | --- |
| `02d515c` | config layer |
| `9d23dd0` | read-only HA102/ESP128 transports |
| `27b10fb` | live snapshot evidence |
| `01fae8f` | verified `DISABLE_OUTPUT` path |
| `2a6eb7c` | manual bench lease |
| `b0d9fb4` | pre/post physical verification |
| `37a3220` | independent HA-ESP and ESP-direct connectors |
| `a57fba2` | physical command target verification |
| `25e311c` | first controlled physical execution path |
| `13def3e` | verified-off transition evidence clarification |
| `d4c8e96` | controlled `OFF -> ON -> OFF` bench flow, battery-aware parameters |
| `caa6811` | wait for post-OFF zero-current confirmation |
| `022e01f` | runbook/checklist timing and battery-selection rules |

Текущий HEAD: `022e01ff9eb2c9421b0e5c39b81c298eff396463`.

## 8. Physical execution status

Готово:

- config, capability discovery и два транспорта;
- snapshots/readback и manual gate/lease;
- battery-aware bench selection;
- короткий физический HA-ESP-RD переход с независимым ESP readback:
  `ON` подтверждён за `1.526 с`, `OFF` за `2.546 с`, нулевой ток — отдельным
  readback примерно через `5 с`;
- evidence и ожидание задержанного readback в executor.

Не сделано:

- полноценный заряд через V3;
- production wiring и автоматическое управление;
- независимый полный `OFF -> ON -> OFF` run через ESP-direct;
- замена V2/V1 UI. V1 UI сохраняется отдельно и является источником
  информационных требований.

При физическом тесте всегда: сначала battery voltage, затем Vset из config,
затем V/I/OVP/OCP readback, manual ARM, короткий ON hold, OFF и ожидание
`Output OFF + current 0 A`.

## 9. Configuration model

```text
config/
  physical/   # transports, connectors, bench profile
  charge/     # recipes and limits
  safety/     # safety ceilings
  runtime/    # tolerances, polling and execution timing
  secrets     # only environment/secret references, never values in git
```

Все изменяемые параметры находятся в config и сопровождаются RU/EN
комментариями. Секреты читаются через environment references.

## 10. Journal/UI

UI — read-only consumer ViewModel. Он показывает stage/phase, параметры,
таймеры, transition evidence, diagnostics, safety, output и хвост журнала.
Журнал имеет однострочные пользовательские записи и отдельные event records;
форматирование не находится в charge engine. V1 UI не удалять и не менять без
отдельной задачи.

## 11. Следующие шаги

1. Завершить независимую physical evidence-проверку ESP-direct.
2. Устранить/задокументировать HA control/readback latency без обхода safety.
3. Подключать runtime state к bot adapter через UserCommand/UI boundaries.
4. Закрыть V3 UI parity с V1 без переноса V1 implementation.
5. Только после parity и bench gates — controlled charge bench.
6. Production migration — отдельное решение после физического evidence.

## 12. Запрещённые направления

- bot direct hardware control;
- параллельные несогласованные FSM;
- обход SafetyEngine, ExecutionPolicy, lease или verified readback;
- hardcoded voltage/current/time/limits;
- synthetic authorization или автоматический fallback между коннекторами;
- изменение ESPHome/firmware/node 101 без отдельного разрешения.

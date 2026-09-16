# V3 Phase 5C — Delta analysis

Статус: analysis only; Delta program не реализован

## Representative decision contracts

Добавлен pure `ChargeDecisionCase` с фиксированными полями case id, battery
profile, measurements, charge state, input config и expected intent.
`DecisionValidationResult` возвращает `MATCH` либо `MISMATCH` с полями
`field`, `expected`, `actual`, `reason`.

Manual и Minimum теперь имеют fixed representative vectors. Они сравниваются с
native `ManualProgram`/`MinimumProgram`, а не с legacy runtime или controller.

Подтверждённые vectors:

- `manual-basic` — target mapping и MANUAL_START;
- `minimum-active` — Minimum остаётся активным;
- `minimum-complete` — переход в Delta и completion.

## Delta states

Перед реализацией Delta необходимо отдельно описать и покрыть:

- entry: получены валидные measurements и начат Delta monitoring;
- hold/observe: накопление подтверждений без premature completion;
- confirmed: evidence достигнута и запущен требуемый hold;
- finish: hold завершён, intent сообщает completion/следующий stage;
- exit/stop: безопасное завершение decision state при stop, invalid или stale
  evidence.

Точные thresholds, confirmation count, timers, CV/CC distinction и reason codes
должны быть перенесены из принятого charge contract отдельными vectors, а не
изобретены в Phase 5C.

## Algorithm vs infrastructure

Algorithm:

- расчёт delta между актуальными observations;
- условия входа/подтверждения/завершения;
- stage transitions;
- completion и reason в `ChargeIntent`.

Infrastructure:

- получение telemetry/measurements;
- Output и setpoint writes;
- HA/RD/ESP transport;
- persistence и restore;
- Telegram/UI;
- lease, ownership и safety enforcement.

Delta program должна быть pure и владеть только первой группой. Все элементы
второй группы остаются внешними boundaries и не могут быть перенесены вместе с
алгоритмом.

## Migration gate

Любой mismatch в representative case блокирует перенос соответствующего
режима до forensic разбора. `MATCH` vectors доказывают только зафиксированные
cases, не полную production parity и не physical safety.

Production controller, FSM, legacy runtime, output, ESPHome/YAML и node 101 не
изменялись.

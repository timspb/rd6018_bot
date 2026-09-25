# V3/V2 Decision Parity Shadow

## Назначение

Этот слой сравнивает decision snapshots, а не исполнение. V2 входом является
только mapping, преобразованный `LegacyDecisionAdapter`; adapter не запускает
legacy controller и не вызывает его tick.

```text
V2 decision mapping → LegacyDecisionSnapshot ┐
                                             ├→ DecisionParityComparator
V3 intent → SafetyDecision → SafeOutputIntent → V3DecisionSnapshot ┘
```

Сравниваются phase, stage, transition, completion, enable, requested voltage,
requested current, safety allowance и violation types. Реальные измерения,
readback, HA state и RD response в parity не входят.

## Mismatch

Результат — `MATCH` или `MISMATCH`. При mismatch сохраняются имена полей,
снимки обеих сторон и причина; автоматических исправлений или приоритета одной
стороны нет. Representative vectors охватывают MAIN, Recovery, MIX, completion
и safety denial. Расширение вектора должно добавлять ожидаемые domain decisions,
не вызов runtime.

## Ownership и ограничения

- LegacyDecisionAdapter владеет только преобразованием входных данных.
- ChargeStrategy формирует V3 `ChargeIntent`.
- SafetyEngine формирует `SafetyDecision`.
- OutputIntentFactory формирует `SafeOutputIntent` только для allowed decision.
- Comparator не имеет RD/HA/lease/actuator доступа.

## Migration blockers

Parity этого этапа не доказывает физическую эквивалентность: отдельно нужны
V2 safety-wrapper/readback/lease parity, отсутствие legacy overwrite и physical
bench validation. Legacy runtime не удаляется и production path не изменяется.

## Отклонения от канона стратегии

- Текущие snapshots отражают только доступные domain decision поля; полная
  V1/V2 трасса переходов требует дополнительных vectors.
- Реальное физическое исполнение намеренно не сравнивается.
- Production controller остаётся источником фактического actuator поведения до
  отдельного migration gate.

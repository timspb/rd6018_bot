# RD6018 V3 Decision Audit Trail Model

Статус: **DECISION_AUDIT_TRAIL_READY**

## Pipeline trace

`DecisionAuditTrail` фиксирует упорядоченную цепочку:

```text
Program selection
  -> Phase decision
  -> Safety decision
  -> Intent creation
  -> Approval
  -> Execution outcome
```

Каждый `DecisionAuditEvent` содержит event/decision/session identity,
timestamp, actor/source, step, result и reason. `approval_id` и `intent_id`
могут быть пустыми только там, где соответствующий объект ещё не создан или
ветка завершилась до этого шага; сам event и причина обязательны.

## Immutability and replay

`DecisionAuditEvent` и `DecisionAuditTrail` — frozen data contracts. Метод
`append()` не изменяет существующий trail, а возвращает новый. Проверяются:

- уникальность event id;
- единая decision/session identity;
- монотонный timestamp;
- отсутствие mutation API.

`replay()` возвращает исходный порядок, completeness и `missing_steps`. Это
позволяет отличить полную цепочку от partial/denied/expired ветки без
додумывания отсутствующих событий.

## Operator explanation

`replay.explanations` даёт пары `step -> reason`, поэтому по trail можно
восстановить выбор программы, фазу, safety result и использованный approval.
Denied и expired approval сохраняются как фактические результаты; физический
успех не синтезируется.

## Verification

Добавлено 6 focused tests:

- full trace and replay;
- denied path;
- expired approval;
- missing event;
- append-only immutability;
- identity/timestamp integrity.

Модель не подключает node 101, RD6018, HA, ESPHome, Modbus или реальные
команды.

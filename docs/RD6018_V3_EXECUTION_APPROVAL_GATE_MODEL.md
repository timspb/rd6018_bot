# RD6018 V3 Execution Approval Gate Model

Статус: **EXECUTION_APPROVAL_GATE_READY**

## Boundary

```text
ExecutionIntent
      |
      v
ExecutionApprovalGate
      |
      +-- no approval / expired / denied safety -> rejected
      |
      +-- SIMULATION -> approval validated, no physical request
      |
      +-- REAL_EXECUTION -> PhysicalExecutionRequest contract only
```

`ExecutionApprovalGate` не вызывает transport, RD6018, HA, ESPHome, Modbus
или physical target. Даже ветка `REAL_EXECUTION` создаёт только immutable
`PhysicalExecutionRequest`; исполнение находится за пределами этой модели.

## ExecutionApproval

Approval содержит:

- `decision_id` и `intent_id`;
- `SafetyDecision`;
- evidence: `current_state`, `telemetry_freshness`, `safety_status`,
  `program_identity`, `lifecycle_state`;
- `approved_by`;
- approval timestamp и expiry.

Идентификаторы approval должны совпадать с `ExecutionIntent.source_decision_id`.
Срок действия строго положительный и проверяется относительно переданного
в gate времени.

## Rules

Без approval request запрещён. `DENY` и `EMERGENCY` safety decisions не могут
пройти gate. Неполное evidence отклоняется при создании approval. В
`SIMULATION` approval можно валидировать для dry run, но physical request не
создаётся.

## Verification

Добавлено 7 focused tests:

- approved contract request;
- missing approval;
- expired approval;
- missing evidence;
- denied safety;
- simulation suppression;
- identity mismatch.

Проверки: `compileall` и `git diff --check`. Node 101, production, V2,
RD6018, HA, ESPHome, Modbus и реальные команды не подключались.

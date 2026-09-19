# RD6018 V3 Recovery Continuity Model

Статус: **V3_RECOVERY_CONTINUITY_READY**

## Recovery snapshot

`V3RecoverySnapshot` — immutable snapshot доменного состояния:

- session/trace identity;
- lifecycle state, program и phase;
- telemetry freshness;
- safety state;
- pending `ExecutionIntent`;
- approval state;
- audit cursor.

Snapshot не содержит transport и не выполняет восстановление физического
состояния.

## Recovery decisions

- `RECOVER_EXISTING` — validated V3 identity присутствует; состояние можно
  восстановить. `execution_allowed` становится `True` только при свежей
  telemetry, `ALLOW/LIMIT`, matching approval и неистёкшем expiry.
- `START_NEW` — snapshot отсутствует и нет legacy state.
- `AMBIGUOUS` — есть legacy state без validated identity. Fake START и fake
  phase transition не создаются.

При missing/expired/mismatched approval, stale telemetry или denied safety
состояние классифицируется как `RECOVER_EXISTING`, но execution запрещён.

## Audit continuity

`AuditContinuityValidator` принимает cursor и immutable audit trail. Он
сохраняет prefix до cursor, проверяет уникальность post-restart events и
отклоняет повторную запись уже существующего event id. Audit trail не
мутируется и не создаёт дубликаты после restart.

## Verification

Добавлено 7 focused tests:

- active charge recovery;
- HOLD recovery;
- denied recovery;
- ambiguous legacy state;
- expired/missing/mismatched approval;
- audit cursor continuation and duplicate rejection.

Проверки выполнены только на synthetic contracts. Node 101, V2, RD6018,
HA, ESPHome, Modbus и physical execution не подключались.

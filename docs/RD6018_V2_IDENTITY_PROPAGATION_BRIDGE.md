# RD6018 V2 Physical Identity Propagation Bridge

Статус: `IDENTITY_BRIDGE_READY`

## Scope

Bridge передаёт correlation metadata между будущим V3 control plane и
существующей V2 execution boundary. Он не вызывает HA, ESPHome, Modbus или RD,
не меняет physical owner и не изменяет V2 execution semantics.

## Contract

```text
V3 ExecutionIntent
        |
        v
ExecutionIdentityEnvelope
        |
        v
V2ExecutionBoundaryRequest
        |
        v
existing V2 owner
```

Envelope содержит:

- `session_id`;
- `trace_id`;
- `decision_id`;
- `intent_id`;
- propagation status.

Все четыре identity поля обязательны для статуса `PROPAGATED`. Bridge только
переносит уже существующие значения и ничего не генерирует.

## Legacy fallback

Для старых V2 START/STOP/SETTINGS операций без identity используется статус
`UNKNOWN_LEGACY_NO_IDENTITY`. Это наблюдаемый fallback, а не synthetic identity.

Частичная identity запрещается статусом `BLOCKED_PARTIAL_IDENTITY`: нельзя
создать корреляцию по неполному набору полей.

## Correlation

Один envelope передаётся одинаково для:

- START;
- STOP;
- SETTINGS changes.

Audit correlation фиксирует operation, envelope, result и reason. Физический
результат и lifecycle events остаются ответственностью существующего V2 owner;
bridge не подменяет их и не создаёт post-factum события.

## Acceptance

- START/STOP/settings contract — defined;
- full identity propagation — supported;
- missing identity — `UNKNOWN_LEGACY_NO_IDENTITY`;
- partial identity — blocked;
- hardware ownership and execution path — unchanged;
- no direct hardware imports/calls.

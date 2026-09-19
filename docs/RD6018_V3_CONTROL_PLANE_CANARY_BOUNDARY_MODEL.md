# RD6018 V3 Control Plane Canary Boundary — WORKSTREAM 90

Статус: `CONTROL_PLANE_CANARY_BOUNDARY_READY`

Модель не подключается к production, node 101, V2 runtime, executor, HA,
ESPHome или Modbus. Реальные команды не включаются.

## 1. Target ownership

```text
V3 Decision Plane
    |
    v
ExecutionIntent
    |
    v
V2 Physical Owner (temporary bridge owner)
    |
    v
RD / HA / ESPHome
```

### V2 остаётся владельцем

- physical commands;
- actuator ownership;
- hardware/readback verification;
- physical rollback and containment paths.

### V3 owns the decision-plane model

- program selection;
- lifecycle and phase decisions;
- canonical safety decision;
- `ExecutionIntent` creation;
- decision/audit provenance.

V3 decision authority не равна physical authority. До отдельного cutover V3 не
имеет прямых HA/ESPHome/Modbus clients и не отправляет actuator commands.

Запрещены два execution owners, параллельный START и direct V3 hardware access.

## 2. Canary modes

### `OBSERVE_ONLY`

V3 читает, нормализует, сравнивает и объясняет. V2 полностью управляет
решениями, physical execution и verification.

### `SHADOW_DECISION`

V3 строит canonical decision и `ExecutionIntent`, но intent не передаётся для
исполнения. V2 продолжает свой обычный путь. Результат сравнения:
`MATCH`, `EXPECTED_DIFFERENCE`, `DIVERGENCE` или `UNKNOWN`.

### `APPROVED_CANARY`

Только после explicit approval gate V3 формирует handoff-ready
`ExecutionIntent`. V2 остаётся единственным physical owner и выполняет через
существующий guarded path. В этой design-only версии режим не активируется.

### `ROLLBACK`

При blocker, unavailable V3, identity mismatch или failed verification:

```text
V3 disabled
    |
    v
V2 continues as sole physical owner
```

Rollback не выполняет автоматическую physical action; он отзывает V3 authority
и сохраняет audit evidence. Фактическое physical recovery остаётся V2 safety
procedure.

## 3. V3/V2 bridge contract

### Input to the bridge

```text
program_id
session_id
trace_id
phase
targets
safety_context
execution_intent
```

Перед handoff валидируются identity, owner, freshness, safety state и
idempotency key. Несовпадение session/trace identity даёт `DENY`.

### Result from the physical owner

```text
accepted
rejected
physical_result
verification
```

`physical_result` и `verification` — observations от V2 owner; V3 не
синтезирует их по факту создания intent.

Контракт не содержит direct HA calls, direct ESPHome calls или direct Modbus
calls.

## 4. Failure and rollback rules

| Событие | Решение |
|---|---|
| V3 unavailable | V2 continues; no V3 handoff |
| V3 differs from V2 | record `DIVERGENCE`; V2 remains owner |
| verification failed | record execution-failure event; no success assumption |
| session identity mismatch | `DENY`; no handoff |
| stale/unknown safety | block canary; preserve current V2 ownership |

Rollback record содержит trigger, previous/current mode, owner, timestamp,
session/trace identity и reason. Session continuity сохраняется в audit trail;
fake START/STOP не создаются.

## 5. Acceptance invariants

- one physical execution owner: V2;
- one active canary mode at a time;
- one session/trace identity chain;
- no V3 physical imports or calls;
- no automatic rollback execution;
- explicit approval required for `APPROVED_CANARY`;
- disabled V3 cannot influence V2.


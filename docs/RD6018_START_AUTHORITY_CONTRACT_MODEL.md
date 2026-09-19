# RD6018 START Authority Contract Model — WORKSTREAM 85

Статус: `START_AUTHORITY_CONTRACT_READY`

Контракт создан в `application/start_authority/` и не подключён к production.

## Contracts

- `StartRequest` — operator intent, program, battery, mode и reference на
  requested parameters. Он не вызывает runtime или transport.
- `StartIdentity` — immutable `session_id`, `trace_id`, `graph_session_id` и
  creation timestamp.
- `SessionStarted` — lifecycle event с identity, program и initial state.
- `StartDecision` — `ALLOW`, `DENY` или `AMBIGUOUS`.
- `PhysicalVerification` — отдельный data-only результат readback; он не
  включает physical execution.

## Boundary

```text
StartRequest
    |
    v
StartAuthority decision
    |
    +-- ALLOW: create identity + SessionStarted
    +-- DENY/AMBIGUOUS: no identity event
    |
    v
future decision/execution boundary
    |
    v
PhysicalVerification (returned later)
```

`SessionStarted` не означает `Output ON`. Только отдельный execution boundary
может вернуть `PhysicalVerification`; lifecycle owner сопоставляет его с
исходным intent. Контракт не содержит HA, ESPHome, RD, Modbus или V2
controller dependencies и не создаёт fake/post-factum events.

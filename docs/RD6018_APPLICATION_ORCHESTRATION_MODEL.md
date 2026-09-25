# RD6018 application orchestration model (Phase 8.0)

Статус: application-only skeleton. Production START, Telegram wiring, HA,
ESPHome, DB, RD transport and physical execution are not connected.

## Flow

```text
OperatorIntent + TelemetrySnapshot
             |
             v
ChargeApplicationService
             |
             +--> SessionManager
             +--> ProfileRegistry
             +--> ChargeEngine
             |
             v
ApplicationDecision
  ├── DomainDecision
  ├── ActuatorIntent (future outer port)
  └── ContainmentResultRequest (future outer owner)
```

## Contracts

`OperatorIntent` is a data-only operator request. It carries source, user and
validated-at-boundary parameters; it is not a controller or physical command.

`TelemetrySnapshot` is an immutable value input containing voltage, current,
temperature, output state and capture timestamp. It contains no reader/client.

`ApplicationDecision` is an immutable result containing acceptance/reason,
logical session snapshot and optional domain decision. The application service
does not execute either `ActuatorIntent` or `ContainmentResultRequest`.

## `ChargeApplicationService` responsibilities

- accept supported operator intents;
- validate the minimum application payload needed to select a profile/session;
- start/stop/pause/resume `SessionManager`;
- select a profile through `ProfileRegistry`;
- convert the value snapshot to domain `Measurements`;
- invoke `ChargeEngine` and return its pure decision.

## Forbidden responsibilities

The service does not contain recipes, threshold algorithms, safety policy,
Telegram/UI state, persistence, HA/ESP clients, RD transport, output commands,
controller calls or physical execution. It does not own the production START
route and is not imported by `bot.py` in this phase.

## Lifecycle semantics

- START creates only a logical session and returns a domain decision.
- REFRESH evaluates a fresh supplied snapshot for an active session.
- STOP returns a containment request; it does not call an owner or issue OFF.
- PAUSE/RESUME change only logical session state.
- Missing/unsupported inputs are rejected without domain or physical side
  effects.

## Boundary status

The next outer phase may add an adapter that consumes `ApplicationDecision`.
That adapter must preserve activation gates, V2 ownership, safety and verified
rollback. No such adapter or composition wiring is part of Phase 8.0.

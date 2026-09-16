# RD6018 domain runtime model (Phase 7.0)

Статус: pure domain runtime skeleton. Production composition, Telegram, HA,
ESPHome, RD transport, persistence и physical execution не подключены.

## Components

### `ChargeEngine`

Owns canonical phase transition validation and lifecycle state updates. It
consumes `ChargeState`, measurements and a selected program/strategy. It returns
pure `ChargeIntent`/`DomainDecision`; it never invokes a transport or actuator.

### `ProfileRegistry`

Owns immutable AGM, EFB and Ca/Ca factory profile definitions and explicit
Custom registration. It returns `BatteryProfile`/recipe data. Custom values must
be supplied explicitly and remain bounded by future safety validation.

### `StrategyEngine`

Owns Main/Recovery/Mix evaluation through the existing pure strategy contracts:
termination evidence, Delta tracking, confirmation counts, holds and authority
timers. It emits `ChargeIntent`, not a command.

### `SessionManager`

Owns only logical `IDLE -> ACTIVE -> PAUSED/STOPPED` lifecycle. It does not
persist, restore, read hardware, or resume physical output. Restart policy stays
outside this skeleton and requires the Phase 5.4 recovery rules.

## Output contract

The domain runtime may return:

- next domain state;
- pure `runtime.charge.decisions.ActuatorIntent` for a future execution port;
- `ContainmentResultRequest` as a request for an outer containment owner;
- completion/reason metadata.

These DTOs have no executor and no infrastructure imports. Their names do not
replace the application/physical containment owners.

## State and transition rules

`ChargeEngine.TRANSITIONS` is the single transition table for this skeleton.
Invalid transitions raise a domain error. Completion/stopped states are
terminal until an explicit logical reset to IDLE.

The strategy layer remains responsible for evidence-specific substates such as
Delta tracking and hold. The engine only coordinates the phase boundary; it
does not duplicate strategy thresholds.

## Dependency rule

```text
validated domain input
        -> ProfileRegistry
        -> StrategyEngine
        -> ChargeEngine
        -> pure domain decision
```

Forbidden imports: `application`, Telegram, HA, ESPHome, RD transport,
persistence, runtime physical/output adapters and UI. No production module
imports this skeleton in Phase 7.0.

## Explicit non-goals

No executor, composition root wiring, persistence adapter, telemetry provider,
START route, ACTIVE gate change, controller call, FSM migration or physical
command is included.

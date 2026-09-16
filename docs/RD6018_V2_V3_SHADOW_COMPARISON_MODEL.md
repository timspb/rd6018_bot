# RD6018 V2/V3 shadow comparison — Phase 9.0

## Scope

`V2V3ComparisonEngine` compares decisions produced by two injected providers.
Both receive the same `ComparisonContext`: telemetry snapshot, configuration
snapshot, session context and trace id.

The engine does not call V2 runtime, V3 execution, controller, FSM mutators,
SafetySupervisor, HA, ESPHome, or physical adapters.

## Compared fields

| Area | Fields |
|---|---|
| Domain | FSM state, phase, profile, strategy decision, target values |
| Safety | limits, warnings, containment recommendation |
| Execution | generated ActuatorIntent representation only |

UI, Telegram formatting and transport details are intentionally excluded.

## Result classification

- `equal` — all comparable fields match;
- `expected_difference` — differences are explicitly listed as accepted for
  the comparison run, such as known EFB Mix budget or CC Delta parity work;
- `conflict` — an unapproved difference, including safety divergence;
- `unknown` — one provider cannot produce a decision snapshot.

`ComparisonResult.equal` is true only for the strict `equal` status. Every
result carries the input trace id and both snapshots for audit correlation.

## Safety and execution boundary

The engine observes safety outputs and actuator-intent data but does not make
safety decisions or execute an intent. V2 remains the current runtime owner;
V3 remains non-authorizing in this comparison phase.

START, ACTIVE, production composition, V2 runtime, HA, ESP and physical
execution are unchanged.

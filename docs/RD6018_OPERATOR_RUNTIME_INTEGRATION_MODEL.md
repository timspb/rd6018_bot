# RD6018 V3 Operator Runtime Integration — WORKSTREAM 31

## Status

`OPERATOR_RUNTIME_READY`.

The composition is read-only:

`Telemetry → ActiveSessionParity → CanonicalTimeline → Diagnostics → ShadowEvidence → OperatorRuntimeView`.

## Operator view

The view presents current profile, phase, state, V/A/W, temperature, source,
confidence, identity status, lease observation, protection state, stale sources,
V2/V3 comparison, divergence and evidence freshness.

`mode=OBSERVE` and `control_enabled=false` are explicit contract fields. There
are no control methods or transport clients in this layer.

## Timeline and diagnostics

Only a timeline whose session identity matches the current observation is
attached. A legacy observation without identity cannot receive a guessed START
or unrelated historical points. Diagnostics are presentation-only and expose
warnings, blockers, stale sources and ambiguity.

## Ownership and safety

V2 remains production decision/execution/physical owner. V3 only consumes
supplied observations. No HA/ESPHome writes, START/STOP, lease operations,
ownership transfer or physical execution are introduced.

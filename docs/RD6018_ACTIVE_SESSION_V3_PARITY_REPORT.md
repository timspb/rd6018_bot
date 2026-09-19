# RD6018 Active Session V3 Runtime Parity — WORKSTREAM 30

## Status

**`ACTIVE_SESSION_PARITY_READY`.**

An already-active Manual session is accepted as an observation input. A START
event, STOP event or complete lifecycle is not required for this parity check.

## Observation model

`ActiveSessionObservation` reconstructs the current profile, phase, state and
telemetry from supplied persisted state plus RD/ESPHome/HA observations.
Missing legacy identity is represented explicitly as `LEGACY_NO_IDENTITY`; it
does not invalidate the active observation.

The previously recorded live state is consistent with this model: active
Manual `Baic72`, phase `MIX`, Output ON, CC telemetry and aligned HA/direct
ESPHome measurements. The historical `stop_reason` is treated as metadata, not
as current state, in accordance with the live consistency report.

## V3 shadow reconstruction

The observer compares current V2 state with a reconstructed V3 view and returns
`MATCH`, `EXPECTED_DIFFERENCE` or `UNKNOWN`. It emits no START, does not create
a fake timeline, and does not infer missing identity.

The UI contract is current-session-only: no stale historical points and no fake
START marker are admitted by the evidence model.

## Safety and ownership

No V3 control, actuator call, lease operation, ownership transfer or physical
command is part of this workstream. V2 remains production decision/execution/
physical owner. `CB-EVIDENCE-001` remains open for the separate full lifecycle
evidence requirement; this workstream removes the incorrect requirement that an
already-active legacy session must have a START event for parity analysis.

# RD6018 shadow evidence persistence — Phase 10.1

## Namespace and purpose

`ShadowEvidenceStore` uses the separate `shadow_evidence` namespace on the
persistence boundary. It stores migration evidence for later analysis, not
runtime state.

Each record contains:

- trace id and timestamp;
- SHA-256 hash of the mirrored input snapshot;
- V2 and V3 decision snapshots;
- comparison result;
- divergence explanation;
- diagnostic event references.

## Restore prohibition

Shadow evidence is historical data. `ShadowEvidenceStore.restore_candidate()`
always rejects. Observed FSM state, active session fields, actuator intent,
lease information or safety information may appear inside an opaque decision
record for analysis, but none is treated as restorable state.

The persistence boundary also classifies `shadow_evidence` as non-domain
history, so the generic restore-candidate path rejects it.

## Operational boundary

The reference store is in-memory only. It performs no file/SQLite write in
this phase and has no HA, ESPHome, controller, FSM mutator, safety or physical
dependency. START, ACTIVE, V2 runtime and V3 execution are unchanged.

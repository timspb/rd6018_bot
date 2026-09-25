# RD6018 telemetry ownership staged migration — Phase 11.0

## Ownership boundary

| Layer | Current owner | Phase 11.0 owner | Scope |
|---|---|---|---|
| physical/control | V2 | V2 | unchanged |
| logical telemetry authority | V2/shared | V3 staged | source arbitration and provenance only |

`TelemetryOwnershipCoordinator` selects the canonical V3 telemetry view from
ESP Direct, then HA, then last-known/unknown through `TelemetryArbitrator`.
It preserves the V2 snapshot and calculates parity evidence for every staged
view.

## States

- `V2_PRIMARY` — initial state; V2 telemetry remains canonical;
- `V3_STAGED` — V3 canonical telemetry view is published to V3 consumers;
- `V2_ROLLBACK` — canonical view returns to the last V2 snapshot.

All staged views retain source, freshness and confidence provenance. Shadow
evidence is held in the coordinator for analysis and is not runtime restore
state.

## Forbidden operations

The coordinator has no control provider and cannot call output commands, HA
writes, ESP writes, execution, START or STOP. It does not mutate V2 FSM,
session or physical ownership. Rollback changes only the logical telemetry
selection state.

V2 runtime and all control ownership remain unchanged.

# RD6018 configuration ownership staged migration — Phase 11.1

## Ownership boundary

| Layer | Phase 11.1 owner | Other owner |
|---|---|---|
| logical configuration | V3 `ConfigurationOwnershipCoordinator` | V2 effective view for parity/rollback |
| domain execution | V2 | unchanged |
| control/physical | V2 | unchanged |

`ConfigurationAuthority` and validated `ConfigurationModel` form the V3
canonical representation. `ConfigurationOwnershipCoordinator` publishes a
snapshot with source provenance and compares it to the V2 effective mapping.

The model covers charge, strategy, safety, containment and transport keys. A
conflict between legacy sources remains an error in `ConfigurationModel`; the
coordinator never selects a hidden precedence.

## States and rollback

- `V3_CANONICAL` — V3 logical configuration view is published for shadow
  consumers;
- `V2_ROLLBACK` — the previously supplied V2 effective view is returned.

Both views and provenance are retained as in-memory shadow evidence. Rollback
changes only the configuration view and does not mutate V2 constants or
runtime behavior.

## Forbidden behavior

The coordinator does not load production runtime, alter constants, call HA or
ESP, execute commands, or make domain/safety decisions. START, ACTIVE, V2
runtime and physical ownership are unchanged.

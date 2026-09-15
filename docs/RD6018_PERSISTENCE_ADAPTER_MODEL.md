# RD6018 persistence adapter boundary — Phase 8.5

## Contracts

- `StateSnapshot` — immutable versioned state payload with owner and capture
  timestamp;
- `PersistenceRecord` — typed envelope separating `DOMAIN_STATE` and
  `HISTORICAL_DATA`;
- `RestoreCandidate` — validated domain candidate that is never marked
  verified by persistence;
- `PersistenceProvider` — save/load/restore-candidate boundary.

## Ownership

Domain state may contain session candidate, FSM state, selected profile and
strategy state. Historical records may contain telemetry and diagnostics
history. Candidate restore is limited to domain owners (`Session Domain`,
`Charge Domain`, `Strategy Domain`).

Containment state, lease state, actuator state, output state and safety state
cannot be restored directly. They require fresh runtime/physical verification
and remain owned by their existing safety/lease/actuator authorities.

## Restore flow

```text
persisted data
      |
      v
schema/owner validation
      |
      v
RestoreCandidate (verified=false)
      |
      v
fresh runtime verification outside persistence
```

The reference `InMemoryPersistenceProvider` is test-only and does not write
files or databases. It demonstrates contract behavior without production
wiring.

## Forbidden dependencies

Persistence does not call or import HA, ESPHome, RD transport, physical
actuators, safety decisions, charge decisions, or production runtime.

START, ACTIVE, Telegram, HA, ESP and physical execution are unchanged.

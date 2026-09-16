# RD6018 Containment Observation Runtime

Status: Phase 3.2 shadow collection only.

## Scope

`ContainmentObservationCollector` converts existing containment-path
observations into immutable `ContainmentObservationRecord` values. It does not
replace or wrap shutdown calls and has no persistence or actuator dependency.

```text
existing event/path identifier
             |
             v
containment_mapping
             |
             v
ContainmentObservationRecord
```

## Collected fields

- `event_id`
- `trace_id`
- `source`
- `trigger`
- `requested_action`
- `verification_state`
- `timestamp`
- `session_id`

## Safety rules

1. Collection is read-only and side-effect free.
2. It does not call HA, ESPHome, lease, controller, FSM, or output methods.
3. Existing emergency shutdown, watchdog, OFF confirmation and lease behavior
   remains authoritative.
4. An unknown path produces an `UNKNOWN` record and does not fail open or
   execute any fallback action.
5. No production writer is connected in Phase 3.2; persistence/aggregation is
   a separate reviewed phase.

## Runtime integration boundary

The collector can consume an event identifier from existing paths, but the
existing paths remain unchanged. The record is evidence for comparison and
diagnostics only, not a command or safety decision.


# RD6018 V3 Operator State Canonical Source Model

Статус: **OPERATOR_STATE_CANONICAL_READY**

## Separation of concerns

- `CanonicalTimeline` отвечает: «что произошло»;
- `OperatorStateSnapshot` отвечает: «что происходит сейчас и почему».

`OperatorStateSnapshot` — immutable read-only aggregation contract для UI. Он не читает journal, history, JSON, SQLite или legacy runtime objects.

## Canonical owners

| Snapshot field | Canonical owner |
|---|---|
| battery identity/profile/chemistry | Battery domain |
| mode/program/targets/policies | ChargeProgram domain |
| current phase/evidence/session identity | Lifecycle domain |
| V/I/W/temperature/CC-CV/timestamp/freshness | Telemetry domain |
| protection/stale/confidence/faults | Safety domain |

## Construction flow

```text
BatteryProfile + ChargeProgram + ChargeLifecycleSnapshot
                    + TelemetrySnapshot + SafetyView
                              |
                              v
                    OperatorStateSnapshot
                              |
                              +--> Operator Dashboard
                              +--> Canonical Timeline view
```

AUTO uses the existing canonical resolver for CALCIUM/EFB/AGM and input aliases `CA_CA`/`KAK`. MANUAL uses explicit `ManualProgramInput`; the Baic72 value is an identity example, not a hardcoded engine branch.

## Explanation

Snapshot carries program identity, current phase, active evidence, waiting conditions and next transition. It can explain the state without re-reading raw sources. Unknown/stale telemetry remains explicit and never creates an inferred transition.

## Lifecycle cases

- active/restored snapshot: carries `session_id` and `trace_id`;
- ambiguous legacy state: `lifecycle_status=AMBIGUOUS`, no fake identity or START;
- fresh telemetry: freshness `FRESH`;
- stale/missing telemetry: explicit `STALE`/`MISSING` state, current phase preserved.

Production runtime, node 101, V2, HA/ESP control, lease control and physical execution were not changed.

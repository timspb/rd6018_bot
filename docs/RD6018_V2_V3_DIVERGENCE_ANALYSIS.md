# RD6018 V2/V3 divergence analysis — Phase 9.1

## Boundary

`DivergenceExplanationEngine` consumes only `ComparisonResult` and its original
`ComparisonContext`. It classifies observed differences and attaches a
source/reason explanation. It does not re-run V2/V3 decisions, change a
configuration, call safety, or execute an actuator intent.

## Categories

- `FSM_DIFF` — state or phase lifecycle;
- `PROFILE_DIFF` — profile/chemistry identity;
- `STRATEGY_DIFF` — termination, Mix budget, Vmax/Delta or current-drop;
- `SAFETY_DIFF` — limits, warnings or containment recommendation;
- `CONFIG_DIFF` — timeout or configuration provenance;
- `ACTUATOR_INTENT_DIFF` — generated intent representation only;
- `UNKNOWN` — unmapped difference or broken trace correlation.

## Known explanations

| Difference | Explanation source | Classification |
|---|---|---|
| EFB 20 h vs 24 h | EFB Mix policy | expected only when explicitly allow-listed |
| CC Vmax/Delta vs current-drop | CC/CV termination policy | expected only during documented parity work |
| watchdog 180 s vs 300 s | watchdog policy | configuration/strategy review required |
| readback timeout variants | readback configuration | configuration review required |

An observed difference is not automatically safe because it is recognizable.
`expected` is inherited only from the comparison engine's explicit allow-list;
otherwise the explanation remains unexpected/conflict evidence.

## Trace rule

The analysis preserves the comparison trace. If the result and context trace
ids differ, it returns `UNKNOWN` with a high-confidence correlation failure
explanation and does not attempt to attribute the data.

Execution is prohibited in this layer. V2 runtime, V3 runtime decisions,
START, ACTIVE, HA, ESP and physical execution are unchanged.

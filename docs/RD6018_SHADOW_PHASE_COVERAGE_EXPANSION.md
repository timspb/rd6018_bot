# RD6018 Shadow Phase Coverage Expansion — WORKSTREAM 97

Статус: `PARTIAL_OBSERVATION`

Режим: `OBSERVE_ONLY`. V2 остаётся единственным production/physical owner.
START, STOP, PAUSE, setpoint changes, lease operations и physical commands не
выполнялись.

## Coverage matrix

| Phase | Real evidence | Program | Targets | Telemetry/safety | V2/V3 parity |
|---|---|---|---|---|---|
| PREP | NOT_OBSERVED | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| MAIN | NOT_OBSERVED | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| MIX | OBSERVED | manual:Baic72 | 17.5 V / 3.5 A | 17.10 V / 3.49 A / protection 0 / lease armed | MATCH |
| HOLD | NOT_OBSERVED | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| SAFE_WAIT | NOT_OBSERVED | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| DONE | OBSERVED as current idle/output-off state only | legacy session stopped | 0 V / 0 A output | protection normal; no active lifecycle proof | UNKNOWN |

## Observed MIX evidence

The real active observation contained:

- program/profile: `Baic72` / Manual;
- phase/lifecycle: `MIX` / `ACTIVE`;
- target: `17.5 V / 3.5 A`;
- measured: `17.10 V / 3.49 A / 59.67 W`;
- safety: protection code `0`, OVP/OCP OFF, lease observed armed;
- V3 shadow: `manual:Baic72`, `MIX`, same target tuple, simulation-only intent;
- parity: `MATCH` for available decision fields.

## DONE qualification

Current Output OFF/zero-output snapshot is a real observation, but it does not
prove a canonical `DONE` lifecycle event. It is therefore not promoted to a
synthetic DONE event. Legacy session identity remains unknown where
`session_id`/`trace_id` are absent.

## Missing coverage

No real correlated evidence was available in this coverage set for PREP, MAIN,
HOLD or SAFE_WAIT. No phase transitions were inferred from targets, telemetry
or old history. The missing phases remain open coverage gaps for a future
natural observation window.

## Side-effect proof

Only existing read-only HA/RD/ESPHome/V2 observations and shadow normalization
were used. No command, write, lease mutation, ownership change or physical
execution occurred.


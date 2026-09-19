# RD6018 V2/V3 Shadow Coverage Matrix

Статус: **V2_V3_SHADOW_COVERAGE_READY**

Режим: V2 остаётся production owner; V3 — read-only shadow observer. Матрица
фиксирует покрытие и пробелы, но не запускает состояния и не реконструирует
legacy identity.

## Coverage legend

- `MATCH` — состояние реально наблюдалось, и V2/V3 decision views совпали;
- `EXPECTED_DIFFERENCE` — расхождение заранее классифицировано как допустимое;
- `DIVERGENCE` — необъяснённое расхождение;
- `UNKNOWN / NOT_OBSERVED` — нет реального evidence для этой комбинации.

## Program × phase matrix

| Program \ Phase | PREP | MAIN | DESULFATION | MIX | HOLD | SAFE_WAIT | DONE |
|---|---|---|---|---|---|---|---|
| CALCIUM | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED |
| EFB | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED |
| AGM | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED |
| MANUAL | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | **MATCH\*** | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED | UNKNOWN / NOT_OBSERVED |

\* Реально наблюдённая комбинация `Manual / Baic72 / MIX` из WS68. Session
identity и trace identity у legacy V2 state отсутствуют, поэтому это parity
match decision fields с partial confidence, а не полная lifecycle evidence.

## Live evidence registry

| Timestamp | Session identity | Program | Phase | Telemetry | Safety | Parity |
|---|---|---|---|---|---|---|
| 2026-09-15 11:03:54 UTC | UNKNOWN — LEGACY_NO_IDENTITY | Manual / Baic72 | MIX | 17.10 V, 3.49 A, 59.67 W, 42 °C | protection 0, lease armed, Modbus age ~0.983 s | MATCH for program/phase/targets/safety/intent |

Source evidence: HA 102 read-only state and node 101 persisted
`manual_session_v2.json`, retrieved through the saved read-only WinSCP
session. Secret values were not exposed.

## Coverage assessment

| Dimension | Observed | Unknown |
|---|---:|---:|
| Program/phase cells | 1 | 27 |
| Full lifecycle chains | 0 | 1 |
| Session identities | 0 validated | 1 legacy identity missing |
| Trace identities | 0 validated | 1 legacy trace missing |
| Physical/control actions | 0 | not applicable by design |

The matrix is ready for future bounded observation windows. It does not claim
that unobserved states are safe, equivalent or available in production.

## Identity rule

Legacy state without `session_id`/`trace_id` remains `UNKNOWN`. It is not joined
to a current timeline, not assigned a synthetic identity and not used to infer
PREP/MAIN/Delta/HOLD/termination transitions.

## Safety and side effects

No deployment, V3 activation, START/STOP, lease operation, HA/ESPHome write,
RD command or physical command was performed. V3 did not influence V2.

## Conclusion

`V2_V3_SHADOW_COVERAGE_READY` means the coverage matrix and evidence schema are
ready. Current real coverage is intentionally narrow: only `MANUAL/MIX` has a
live parity observation; all other cells remain explicitly unknown.

# RD6018 V3 Operator Diagnostics & Decision Explanation — WORKSTREAM 32

## Status

`OPERATOR_EXPLANATION_READY`.

## Contracts

`DecisionExplanation` describes current state/phase, explicitly supplied
strategy/reason/evidence, confidence and an explicitly evidenced next
transition. Missing facts remain `UNKNOWN`; the layer never guesses.

`PhaseExplanation` separates why a phase was entered, why it remains active,
transition conditions and unmet conditions.

`SafetyExplanation` presents safety state, protections, stale data and blockers.
Historical faults are carried separately and are not treated as active faults.

## Operator integration

`OperatorRuntimeView` now accepts the explanation object and exposes unknown
reasons. This is presentation-only. V2 remains production owner and the
operator surface has no control, START/STOP, lease or physical path.

## Shadow comparison

The explanation preserves `MATCH`, `EXPECTED_DIFFERENCE` or `UNKNOWN` from the
V2/V3 parity result and does not convert a difference into a command.

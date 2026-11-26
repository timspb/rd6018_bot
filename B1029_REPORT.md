# B1029 — real Vset/Iset write-completion causal evidence

Run: `rd6018-b1029-20261126-r73-vi-write-causality`
Branch: `codex/rd6018-b1029-vi-write-causality-20261126`
Exact base/code HEAD: `56a42c097d0bd753f124a8a98be56246ded1f50d`
Result: **NO PRODUCTION CHANGE; TERMINAL RECEIPT UNAVAILABLE; P3/P8 HOLD**

## Decision

The source audit found no honest backwards-compatible observation seam to
implement within current hardware write routes. Existing `ExecutionPort`
setters and both safety setter layers expose bools. The default HA102 connector
only receives an HA service HTTP status; the ESP Native number command has no
per-write request ID or terminal completion receipt. The direct Native
connection generation and read-only Vset/Iset callback records do not supply
the missing command completion boundary. Therefore I stopped before changing
production code or adding parity tests that could imply unsupported receipt
semantics.

The existing V-then-I ordering, serialization, adopted-write ratchet, recovery
and HANDS_OFF behavior, safety limits, and Output ON route are unchanged. No
receipt was fabricated from bool success, an HTTP response, a guessed clock
sample, or a later cache/callback read. The B1027 pure validator remains
untouched.

## Verification

- Focused unchanged validator suite: **6/6 PASS** using the requested
  `/home/home-pc/.venvs/pcp-test/bin/python`, `PYTHONPATH=.:tests:tools`, and
  inert `TG_TOKEN`.
- No production code or tests changed, so no source parity, py_compile, or
  source diff verification is claimed.
- No physical, HA/ESP, node104, firmware, service, Output/setpoint, lease,
  deployment, network/GitHub, full-suite, commit, or push action occurred.
- Existing Draft PR #182 was not merged or modified remotely. No shared
  runbook/checkpoint/master/handoff files were edited.

Detailed call graph and minimal future prerequisite: see
[`docs/acceptance/B1029_NATIVE_WRITE_CAUSALITY.md`](docs/acceptance/B1029_NATIVE_WRITE_CAUSALITY.md).

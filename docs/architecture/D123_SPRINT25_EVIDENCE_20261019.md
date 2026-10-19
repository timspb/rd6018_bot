# D123 Sprint 25 — DESULFATION completion dispatch convergence

## Scope and baseline

Source-only, one bounded P3 cut from exact clean HEAD
`fafca1bf8c142d911c6b0350c8083a939fa48ab5`. The existing
`runtime.charge.runtime.desulfation_completion` owner now owns typed-input and
event-end assembly plus build/apply dispatch for
`DesulfationAction.COMPLETE_TO_SAFE_WAIT`. `ManagedChargeController` retains
`decide_desulfation` and `_main_target(temp)` target selection. No compatibility
facade was added.

The caller preserves
`AuthorityDecision(CONTINUE, 'desulfation_completion_session_identity_invalid')`
when the owner rejects identity or capture/build. The owner keeps session ID
and generation, DESULFATION/SAFE_WAIT/MAIN stages, recovery attempt, AGM step,
targets, clocks, sample values, event-end payload, action keys/values and commit
order. Event-end capture/build failure occurs before mutation/action updates.
The owner has no RD setter or execution-port route. SAFE_WAIT recovery/final,
MAIN, MIX, tick, P2 and P4 are outside scope.

## Guards

`tests/test_d123_p3_desulfation_completion_effect.py` covers profile target and
continuation parity, action payload, session identity rejection, duration gate,
controller-level dispatch parity, event-end capture failure with read-only
state/actions, AST single dispatch/build/apply and owner import/writer guards.

## Validation

- Focused Python 3.12: **14 passed** (`test_d123_p3_desulfation_completion_effect`,
  `test_desulfation_ownership_cutover`).
- Full offline Python 3.12 discovery with synthetic `TG_TOKEN=123456789:d123-sprint25`:
  **2,415 passed, 3 skipped**.
- `/home/home-pc/.venvs/pcp-test/bin/python -m compileall -q .`: **PASS**.
- `git diff --check`: **PASS**.

The focused `test_voltage_relaxation_real_session_contract` was not included in
the successful focused invocation because this checkout lacks its local helper
module `d123_final_safe_wait_helpers`; the complete discovery itself passed.

No node104, ESP, HA, deployment, GitHub, or physical actions were performed.

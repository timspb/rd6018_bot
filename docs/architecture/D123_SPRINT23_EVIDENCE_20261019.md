# D123 Sprint 23 — MAIN completion dispatch

Baseline: exact clean HEAD `67c670238c4370ab45bb83ab8604e47cdcdec51c`.

## Bounded change

The `AuthorityAction.COMPLETE_TO_SAFE_WAIT` MAIN branch in
`ManagedChargeController._apply_authoritative_decision` still obtains the
Storage target through `_storage_target()` and keeps `decide_main_transition`
as its decision source. It now calls
`runtime.charge.runtime.final_safe_wait_entry.apply_main_completion_to_safe_wait`
once. That existing owner assembles the unchanged typed final SAFE_WAIT input,
captures the existing event-end payload, and dispatches the existing
single-applicator effect.

If the owner rejects stale or invalid identity, the controller retains its
existing `final_safe_wait_entry_session_identity_invalid` STOP_AND_DIAGNOSE
containment. No other action branch moved. No strategy, recipe, schema, Guard,
lease, safety, execution-port, or physical-writer ownership changed. The owner
contains no direct RD setters or execution-port access.

Focused guards cover Ca/Ca, EFB, and AGM target/action parity, stale identity
rejection without mutation or intent, one AST-counted controller dispatch, no
inline typed-input construction, and the existing single effect applicator / no
physical-writer checks.

## Verification

Interpreter: `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` — Python 3.12.3.
All test commands used synthetic `TG_TOKEN=123456789:d123-sprint23`.

- Focused: **41 tests passed** across final SAFE_WAIT entry, MAIN authority,
  charge authority, MIX timeout, relaxation session contract, and final
  SAFE_WAIT transaction suites.
- Full offline discovery: **2,410 tests passed, 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

Source-only worktree. No node104, ESP, HA, deployment, GitHub, or physical
actions were performed. This is not physical acceptance or P3 completion.

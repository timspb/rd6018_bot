# D123 Sprint 24 — MAIN entry dispatch convergence

Baseline: exact clean HEAD `4662f54d4f0af722f9b96b246e83658d97df5a7a`.

## Bounded source cut

`decide_main_transition` remains in
`ManagedChargeController._apply_authoritative_decision`. The controller keeps
`_desulf_target(temp)`, `_mix_target(temp)`, and MIX `_add_phase_limits`
selection. On each corresponding decision, it now calls the existing
`runtime.charge.runtime.desulfation_entry.apply_main_desulfation_entry` or
`runtime.charge.runtime.mix_entry.apply_main_mix_entry` once. Each owner
assembles its existing typed effect input and event-end payload, then invokes
the existing effect applicator once.

The established action keys and values, target/protection limits, attempt
count, stage-history edge, clocks, resets, phase-current mirrors and algorithms
are unchanged. Event-end capture failure occurs before stage mutation and action
updates, matching the former input-construction order. The owners have no RD
setter or execution-port dependency. AGM step advance, MAIN completion,
STOP_AND_DIAGNOSE and tick were not changed.

Focused tests in `test_d123_p3_main_desulfation_effect.py` and
`test_d123_p3_main_mix_effect.py` verify Ca/Ca, EFB and AGM parity, capture
failure without mutation/action application, and AST guards for one controller
dispatch with no inline input/effect construction. Existing effect tests retain
the action/state reset checks.

## Verification

Interpreter: `/home/home-pc/rd6018-v3-deploy/.venv/bin/python` — Python 3.12.
Commands used synthetic `TG_TOKEN=123456789:d123-sprint24`.

- Focused authority/effect/transaction coverage: **48 tests passed**.
- Full offline discovery: **2,414 tests passed, 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.

Source-only worktree. No node104, ESP, HA, deployment, GitHub, or physical
actions were performed. This is software evidence, not physical acceptance or
P3 completion.

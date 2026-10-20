# D123 Sprint 32 — MAIN authority orchestration ownership

## Scope and baseline

Source-only work started at exact clean HEAD
`b4c8440736fc5f9b5e1f447b22352dcddbac1db1` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Moved MAIN decision input assembly and the complete MAIN action dispatch from
`ManagedChargeController._apply_authoritative_decision` into the existing
`runtime.charge.runtime.main_scaffold.apply_main_authority_tick` owner.
The controller still performs authoritative-stage/current-stage admission and
delegates once. The owner calls the unchanged pure
`runtime.charge.strategy.main_authority.decide_main_transition` and dispatches
its five existing outcomes through the existing typed effect owners:

- AGM step advance;
- MAIN -> DESULFATION;
- MAIN -> MIX;
- MAIN -> final SAFE_WAIT;
- STOP_AND_DIAGNOSE.

Decision inputs, stage/profile target selection, effect applicators, action
payloads, session mutation and persistence ordering, identity-failure
containment, and downstream application execution/verified transactions are
unchanged. No recipe, threshold, Guard, lease, safety, or hardware writer moved.
The owner has no `ExecutionPort`, RD setter, or Output command dependency.

## Validation

- Focused MAIN/effect/controller authority regression: **38 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint32`: **2,426 PASS / 3 skipped**
  (**2,429 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. Controller stage routing and DESULFATION/recovery/final
SAFE_WAIT dispatch, tick evidence/trace assembly, terminal persistence
ownership, and Manual integration remain outside this cut. `runtime.production_runtime`
still constructs and calls `ManagedChargeController`; do not start P4 until
P2/P3 convergence is convincingly complete. No physical acceptance or
deployment is claimed.

# D123 Sprint 37 — retire MIX compatibility router

## Scope and baseline

Source-only work started at exact clean HEAD
`1aaefab2990d459e934b82605d977a5ee5956224` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Removed `ManagedChargeController._handle_mix_stage_override`, a
characterization-only compatibility hook with no production or test call
sites. Added a regression asserting the obsolete method stays absent. MIX
authority remains on the modular `tick` path and existing mix scaffold; no
decision, execution, or physical transaction behavior changed.

## Validation

- Focused MIX/SAFE_WAIT/transaction regression: **38 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint37`: **2,427 PASS / 3 skipped**
  (**2,430 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. Tick evidence/trace assembly, terminal persistence,
Manual integration, and P2 Guard restore admission remain. `runtime.production_runtime`
still constructs and calls `ManagedChargeController`; do not start P4. No
physical acceptance or deployment is claimed.

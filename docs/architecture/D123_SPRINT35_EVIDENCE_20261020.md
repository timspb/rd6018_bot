# D123 Sprint 35 — final SAFE_WAIT authority ownership

## Scope and baseline

Source-only work started at exact clean HEAD
`eb8a30bf32f09ee122491a6602ba5ee142378dd1` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Moved final SAFE_WAIT OFF-sample gating, continuation validation, fail-closed
STOP_AND_DIAGNOSE handling, Storage request dispatch, and decision logging to
`runtime.charge.runtime.final_safe_wait_authority.apply_final_safe_wait_authority`.
Both existing controller routes delegate to this owner; the controller method
is removed. The existing immutable effect builder remains the strategy/action
owner. Invalid continuation containment and the exact Storage request/token
are unchanged. Verified DONE commit, output execution, lease, and the physical
enable transaction remain with their existing owners; no direct RD setter was
added.

## Validation

- Focused final SAFE_WAIT/MIX/transaction/recovery regression: **30 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint35`: **2,426 PASS / 3 skipped**
  (**2,429 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. Outer stage routing, tick evidence/trace assembly,
terminal persistence ownership, and Manual integration remain outside this cut.
`runtime.production_runtime` still constructs and calls
`ManagedChargeController`; do not start P4 before P2/P3 convergence is
convincingly complete. No physical acceptance or deployment is claimed.

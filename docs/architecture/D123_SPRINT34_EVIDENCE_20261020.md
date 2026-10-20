# D123 Sprint 34 — recovery SAFE_WAIT authority ownership

## Scope and baseline

Source-only work started at exact clean HEAD
`d1e128a3154708527b025a9c912ac59402d898e2` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA,
deployment, GitHub, firmware, recipe, threshold, or physical operation was
performed. P2 MAIN Guard restore admission remains fail-closed and deferred.

## Ownership cut

Moved recovery SAFE_WAIT continuation validation, strategy decision, and
enable-request construction from `ManagedChargeController` into the existing
`runtime.charge.runtime.recovery_scaffold.apply_recovery_safe_wait_authority`.
Both existing controller routes delegate to that owner; the controller method
was removed. The exact stage/session/generation/attempt/AGM validation,
fail-closed `STOP_AND_DIAGNOSE`, output-off sample gate, strategy inputs,
action keys, phase limits, verified-enable transition token, log event, and
decision reasons are preserved. The request still flows through the existing
application execution and verified physical transaction owners. No direct RD
setter or ExecutionPort was added.

## Validation

- Focused recovery/SAFE_WAIT/transaction regression: **30 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint34`: **2,426 PASS / 3 skipped**
  (**2,429 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).

## Remaining boundary

P3 remains partial. Final SAFE_WAIT authority, outer stage routing, tick
evidence/trace assembly, terminal persistence ownership, and Manual integration
remain outside this cut. `runtime.production_runtime` still constructs and
calls `ManagedChargeController`; do not start P4 before P2/P3 convergence is
convincingly complete. No physical acceptance or deployment is claimed.

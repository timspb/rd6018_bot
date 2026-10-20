# D123 Sprint 31 — MIX authority orchestration ownership

## Scope and baseline

Source-only work started from exact clean HEAD
`5f5f2b42c9d14c820d2968f3381c6aae5b052db0` on
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA, deployment,
GitHub, recipe, threshold, or physical operation was performed. P2 MAIN Guard
restore admission remains fail-closed and deferred.

## Manual integration audit

Production Manual remains an independent program family. Production bootstrap
registers `ProductionManualSessionManager` and `ProductionManualUIRoute`; Manual
START routes submit through the route to the manager, and STOP/discard ownership
remains in the Manual manager/application route. No active AUTO decision/state
or recipe coupling from `ManagedChargeController` into Manual was found. This
was recorded as an audit result only; no Manual code changed.

## Ownership cut

Moved the complete MIX authority branch from
`ManagedChargeController._apply_authoritative_decision` to the existing
`runtime.charge.runtime.mix_scaffold.apply_mix_authority_tick` owner:

- MIX evidence mirror projection;
- `decide_mix_transition` call and input assembly;
- finish-hold effect build/apply and evidence log;
- MIX completion target selection and SAFE_WAIT entry dispatch;
- stale identity STOP_AND_DIAGNOSE containment and decision STOP dispatch.

The controller retains stage/current-stage admission and one call to the owner.
The MIX owner does not import or invoke `application.execution_port`, RD setters,
or ON/OFF commands. MAIN, DESULFATION, recovery/final SAFE_WAIT dispatch,
recipe/target/protection selection outside the moved MIX branch, persistence,
lease, readback, and application execution are unchanged. Existing
`application.execution_port` remains the sole physical writer.

Focused source/parity/failure/static set: **29 tests passed**. This includes
MIX finish evidence parity, mirror ownership, SAFE_WAIT completion and stale
identity containment, MAIN/MIX branch parity, controller authority failure
handling, and static one-dispatch/no-writer guards.

## Validation

- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint31`: **2,423 passed / 3 skipped**
  (**2,426 tests run**).
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Python environment: `/home/home-pc/rd6018-v3-deploy/.venv` (Python 3.12).
- Full suite output: `/tmp/d123-sprint31-unittest-final.log`.

## Next gate

Inspect remaining central `_apply_authoritative_decision` MAIN/SAFE_WAIT
orchestration and tick evidence/trace glue for one bounded ownership move into
existing owners. Do not start P4. Keep ordinary restore snapshot ownership and
P2 MAIN Guard restore admission fail-closed/deferred until a safe seam avoids
that boundary. Manual remains separate from AUTO.

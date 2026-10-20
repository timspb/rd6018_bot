# D123 Sprint 39 — canonical stage dispatch and production subclass parity

Baseline: `d8d4b962ea31836d7b4c84ff10a44569645b82c6`. Worktree: isolated WSL2 source checkout `rd6018-d118-start-lease-repair-20261019`. Scope remained source/tests/docs only; no HA, ESPHome, production service, credentials, firmware, or physical hardware was accessed or changed.

## Change

- Added `runtime/charge/runtime/stage_authority.py` as the single stage router to the already-existing MAIN, MIX, DESULFATION, recovery SAFE_WAIT, and final SAFE_WAIT owners.
- `ManagedChargeController` now delegates its stage hook to that owner; it no longer carries the branch-by-branch authority route.
- Removed `AutoStrategyProductionChargeController`'s superseded MAIN decision and dispatch overrides. `DiagnosticProductionChargeController` now invokes the existing MAIN owner with its diagnostic veto callback, while `MixActiveAuthorityMixin` preserves its durable active-time projection around the canonical route.
- Added a production-subclass regression: a normal MAIN `ENTER_MIX` decision reaches the existing MIX effect owner; confirmed failed-cell evidence vetoes the same decision to `STOP_AND_DIAGNOSE` with `turn_off`, no `turn_on`, and no voltage write.
- Updated architecture tests to check the new owner boundary rather than obsolete direct controller call sites.

This closes one P3 routing/duplicate-subclass-dispatch cut only. P3 remains incomplete: `tick` orchestration and mutable action dictionaries still live on the transitional controller; Manual integration and broader session/DONE ownership remain open. P4 facade removal is not attempted here.

## Verification

- Focused stage-owner, transaction, restore, lease, diagnostic, and production-subclass set: **79 tests PASS**.
- Full offline Python 3.12 unittest discovery: **2,432 tests PASS, 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Live / physical acceptance: not run; no production mutations.

Synthetic test token only: `TG_TOKEN=123456789:d123-sprint39`.

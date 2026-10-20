# D123 Sprint 41 — application session/stage tick ownership

Status: source-only P3 orchestration cut; no production, HA, ESPHome, or physical bench access.

## Change

- Moved the production session-tick orchestration from `ManagedChargeController.tick` to `application.charge_session_tick.run_charge_session_tick`. The controller method is now a compatibility handoff.
- Moved admitted stage selection to `application.charge_stage_tick.run_charge_stage_tick`; the active application tick calls this owner directly. The controller scaffold route is a compatibility handoff only.
- Preserved the existing decision/effect owners, runtime owner-lock scope, application execution transaction, and physical safety boundary. No actuator write was introduced in either new application module.
- Moved verified recovery SAFE_WAIT -> MAIN continuation validation and state/persistence commit to a frozen `RecoverySafeWaitCompletionEffect` in `runtime.charge.runtime.recovery_safe_wait_completion`. Session ID, start timestamp, session generation, active-generation checks and ordering of state mutation before canonical save remain guarded. The controller callback only builds/applies the typed effect after the existing verified-ON receipt path.
- Added production Manual boundary integration coverage and updated architecture guards to assert application ownership of tick, stage routing, trace assembly, and STOP_AND_DIAGNOSE dispatch.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused stage/recovery/transition/Manual/trace set: **42 PASS**.
- Full offline unittest discovery: **2,438 tests, 3 skipped, 0 failures**.
- `git diff --check`: required before commit.
- Existing tests use synthetic local data/token only; no live service or physical control was used.

## Boundary

P3 stage/session-tick orchestration is complete at this cut. This does not claim P2 completion: MAIN Guard restore admission and broader canonical session/audit lifecycle ownership remain open and fail-closed. P4 transitional-facade elimination and P5 release/multi-version/production acceptance also remain open. Physical behavior is not validated by this source-only sprint.

# D123 Sprint 45 — MIX active-time tick ownership

Status: source-only P4 slice; no production, HA, ESPHome, or physical bench access.

## Change

- Moved durable MIX active-time observation and post-transition activation/deactivation from `MixActiveAuthorityMixin.tick` into `application.charge_session_tick`.
- Preserved the conservative rule that unknown Output is charged as active, post-transition activation may slightly over-count rather than extend HV authority, and only `MixActiveAuthorityError` is swallowed when recording inactivity.
- Removed the Mixin's `tick` override and strengthened the architecture gate.

## Verification

- Python 3.12 `compileall`: PASS.
- Focused Mix authority/timeout/preemption/HANDS_OFF set: **22/22 PASS**.
- Full offline unittest discovery: **2,441 tests, 3 skipped, 0 failures**.
- No production service, HA, ESPHome node, or physical equipment was contacted or changed.

## Boundary

The production `charge_controller.tick` dispatch remains because `ProductionChargeController.tick` still owns cooling-pause capture/resume around the application handoff. That wrapper must be migrated with its full cooling state contract before removal. P2 Guard restore admission remains fail-closed/deferred; P5 multi-version/release gates and physical acceptance remain open. Python 3.10/3.11 are unavailable locally.

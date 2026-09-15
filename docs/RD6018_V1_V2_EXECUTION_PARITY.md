# RD6018 V1/V2 Execution Parity Audit

Status: Phase 5.0 read-only audit. No runtime behavior, configuration or
physical execution was changed.

## Scope and terminology

**V1** means the historical monolithic runtime represented by the baseline
`ChargeController`/`bot.py` path. **V2** means the current production
composition: `bot.py` plus `runtime.v2_runtime`, `v2_bootstrap`, the V2
controller hierarchy, safety wrappers, ownership managers and edge lease.

`bot_legacy.py` is currently a rollback compatibility shim, not an independent
production polling owner.

## Execution path comparison

| Area | V1 | V2 | Difference | Risk | Recommendation |
|---|---|---|---|---|---|
| Entrypoint | One monolithic `bot.py` constructed Bot, HA client, controller and tasks | Small `bot.py` imports the legacy runtime namespace and applies many installers before `main()` | V2 has composition order and module-alias coupling | High: late wrappers can replace functions or cached bound methods | Freeze installer order and object identity before further extraction |
| Controller initialization | Direct `ChargeController(HassClient)` | `DiagnosticProductionChargeControllerV2` -> Auto strategy -> V2/legacy controller scaffold | V2 adds strategy and diagnostic layers while retaining inheritance | High: V2 still executes legacy `super().tick()` mechanics | Keep legacy mechanics as characterized scaffold until side effects are fully audited |
| Session creation | Controller initializes `charge_session.json` and in-memory stage state | Auto still uses controller session; Manual uses separate `ProductionManualSessionManager` and `manual_session_v2.json` | V2 has multiple session authorities | High: restore/manual/controller state can disagree | One declared writer/reader map per session type |
| FSM | One `ChargeController` FSM owns stages | V2 owns Main/Mix decisions but legacy FSM/mechanics remain underneath | Split decision/mechanics ownership | High: masked legacy transitions may still perform side effects | Preserve one FSM owner and test every `super().tick()` side effect |
| Safety | Direct HA/runtime checks around the monolithic loop | Layered `runtime_safety`, V2/strict guards, SafeOutput and lease | V2 has stronger boundaries but more overlapping owners | Medium/High: duplicate shutdown and inconsistent evidence states | Normalize outcomes before changing owners |
| First enable | Read live state, initialize controller, calculate initial target, then direct safe/HA enable | Preflight/recipe/ownership checks, controller start, `safe_enable_output`, readback and lease guard | V2 adds ordering gates and physical verification | Medium: more rejection/race points | Keep V2 enable order; test startup race separately |
| Output owner | Monolithic runtime/HA client path | V2 safety-composed HA surface plus SafeOutput and independent edge lease | Physical authority is layered | High: direct legacy calls remain reachable through wrappers | Do not mechanically replace calls; prove live composition first |
| Telegram path | Handler directly called controller/start logic | V2 UI adapters compose over legacy handlers; current START is dry-run/gated | More route and callback layers | Medium: duplicate/old handlers can diverge | Maintain one authoritative route inventory |

## START flow

### V1 reference path

```text
Telegram callback
  -> parse profile/capacity
  -> read HA live state
  -> ChargeController.start()
  -> select PREP/Main target
  -> write safe setpoints/output
  -> controller tick owns subsequent FSM decisions
```

The path was short, so startup ordering and failures were easier to observe. It
also had fewer independent ownership and rollback barriers.

### V2 current path

```text
Telegram/UI
  -> V2 composition/handler
  -> ownership and preflight checks
  -> DiagnosticProductionChargeControllerV2
  -> ChargeControllerV2/legacy mechanics
  -> recipe/strategy decision
  -> SafeOutputCoordinator + runtime safety
  -> HA/edge lease/physical boundary
```

V2 improves protection ordering and readback, but the controller and legacy
runtime remain coupled through inheritance and shared module state.

## Charge program parity

| Program | V1 | V2 | Difference | Risk | Recommendation |
|---|---|---|---|---|---|
| AGM | Main, temperature compensation, legacy recovery/Mix transitions | V2 chemistry/intent authority, AGM Main progression and bounded Mix; legacy scaffold still executes mechanics | V2 masks ordinary legacy transitions and adds evidence/budget rules | Medium: parity depends on masking and shared state | Compare transition traces, not only final setpoints |
| EFB | Legacy Main/recovery/Mix behavior | V2 envelope and explicit EFB ceiling/budget; generic EFB HV is bounded at 16.5 V | V2 narrows/clarifies authority | Medium: old constants and new recipe envelope can drift | Keep V2 envelope authoritative; test all boundary values |
| Ca/Ca | Legacy Main and Mix/recovery behavior | V2 Ca/Ca recipe, bounded Mix and durable active-time authority | V2 adds durable budget and explicit completion evidence | Medium: persisted active-time/restart behavior is new | Validate restart and Mix timeout separately |
| Custom | Legacy custom parameters and legacy FSM mechanics | Remains legacy-authoritative by design, with V2 safety/ownership wrappers | Less V2 strategy normalization than standard profiles | High: Custom has the least parity coverage and most direct legacy surface | Keep compatibility path isolated and inventory every actuator call |

### Finish semantics

V1 used legacy stage and delta logic in one controller. V2 explicitly separates
CV current evidence (`Imin -> confirmed ΔI`) from CC voltage evidence
(`Vmax -> confirmed ΔV`), adds sticky Mix hold and chemistry authority ceilings.
These are intentional behavioral changes, not simple refactoring.

## Failure handling

| Failure | V1 | V2 | Difference | Risk | Recommendation |
|---|---|---|---|---|---|
| HA loss | Monolithic logger/watchdog could directly stop Output and controller | HA-loss recovery state, watchdogs, runtime safety, bounded recovery and edge lease coexist | V2 distinguishes telemetry loss from physical dead-man loss | High: overlapping timers/owners can disagree | Keep one containment result and correlate all paths |
| Telemetry stale | Controller/logger used the available HA snapshot | Multiple freshness/readback checks plus shadow direct telemetry and lease evidence | More evidence sources and failure states | High: stale/unknown evidence can be interpreted differently | Keep direct evidence read-only until authority is proven |
| Readback failure | Direct operation failure/exception path | SafeOutput transaction, runtime guards, positive OFF confirmation and `OFF_UNCONFIRMED` containment | V2 is safer but more stateful | Medium/High: command acknowledgement is not physical proof | Preserve conservative OFF semantics |
| Stop | Handler/runtime stopped controller and requested HA OFF | Manual manager, controller, operator-managed stop and safety wrappers can all participate | Multiple stop owners | Medium: race and duplicate notification | Normalize observation first; do not deduplicate action yet |
| Restart | Startup initialized DB/HA and attempted `try_restore_session()` | Startup authority reconciliation, deferred restore, durable ownership and lease checks | V2 introduces a restart/authority race surface | High: known confirmed functional defect | Treat restart/restore as a separate release gate |
| Rollback | Simpler process/config rollback to monolithic runtime | UI/authority flags, compatibility shim, ownership/lease state and persisted files | V2 rollback is not a single state transition | High: old state/DB/lease may not match selected code path | Require exact SHA/config/state compatibility before rollback |

## Ownership comparison

| Owner | V1 | V2 | Assessment |
|---|---|---|---|
| FSM | `ChargeController` | V2 strategy plus `ChargeControllerV2`/legacy FSM scaffold | V2 split is the largest semantic complexity source |
| Session | Controller and `charge_session.json` | Controller session plus Manual manager/session JSON plus ownership state | V2 has stronger recovery evidence but more drift risk |
| Safety | Monolithic runtime/HA checks | runtime safety layers, SafeOutput, guardrails, lease and ESPHome | V2 protection is stronger, ownership is more distributed |
| Output | Direct HA client path | SafeOutput/runtime safety composed HA surface; ESPHome lease independent | V2 has better verification and a separate dead-man, but legacy callers remain |
| Telemetry | HA read path in main logger | HA, readback wrappers, shadow/direct ESP and edge lease evidence | V2 source arbitration is not yet fully canonical |

## Why V1 appeared more stable

1. Fewer modules and no installer-order dependency.
2. One controller/session/FSM state model.
3. One primary telemetry loop and simpler failure interpretation.
4. Fewer ownership transitions and persisted state contracts.
5. Less separation between decision and execution, so fewer correlation gaps.

This simplicity also meant weaker isolation, less positive readback evidence,
less independent dead-man protection and poorer HANDS_OFF/recovery semantics.

## V2 risk introduced by migration

- module-as-app aliasing and many monkey-patch installers;
- V2 strategy decisions layered over legacy `super().tick()` mechanics;
- multiple session and persisted-state authorities;
- overlapping watchdog, safety, containment and lease owners;
- richer restart/recovery path with a confirmed restore race;
- direct legacy actuator call sites still present behind wrappers;
- Custom profile remains less normalized than standard profiles;
- V2/V3 contract drift can be mistaken for harmless presentation refactoring.

## Final assessment

V1 was more stable primarily because its execution graph was smaller and more
centralized, not because its safety model was stronger. V2 preserved most V1
charge mechanics while adding valuable safety, ownership and evidence layers;
the migration risk comes from combining both graphs before fully separating
their authorities.

Recommended direction is **current V2 with targeted stability fixes**, not a
blind V1 rollback. The first blockers before further execution migration are:

1. startup/restore race proof and fix plan;
2. single authoritative session/FSM ownership map;
3. containment and actuator result correlation;
4. real production-composition evidence, not only unit/source tests;
5. preserved V1/V2 parity tests for every chemistry and failure path.


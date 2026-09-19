# RD6018 Execution Plane Consolidation Plan

Status: `PLAN_ONLY`

No code, merge, deployment, or hardware action was performed.

## Goal

Keep exactly one production physical execution owner: the existing V2 owner
and its verified HA/RD path. Treat the accumulated V3 output/physical tree as
contracts and candidate adapters until an explicit migration proves otherwise.

## Current execution inventory

| Source/action | Decision owner | Current execution owner | Adapter/transport | Hardware | Disposition |
|---|---|---|---|---|---|
| `runtime/v2_runtime.py` `set_voltage` / `set_current` | V2 runtime/controller | V2 physical owner | `HassClient` | RD6018 through HA | **KEEP** |
| `runtime/v2_runtime.py` `turn_on` / `turn_off` | V2 runtime/controller and safety/recovery paths | V2 physical owner | `HassClient` | RD6018 output | **KEEP** |
| `runtime/v2_lifecycle.py` writes | V2 lifecycle/controller | V2 physical owner | `app.hass` | RD6018 through HA | **KEEP, inventory under V2** |
| `runtime/v2_startup_recovery.py` writes | V2 recovery authority | V2 physical owner | `app.hass` | RD6018 through HA | **KEEP, safety-reviewed** |
| `manual_mode.py` `safe_enable_output()` | Manual session manager | Direct V2 `HassClient` path | HA/RD | RD6018 output | **MIGRATE to one V2 execution port** |
| `manual_mode.py` normal/error `turn_off()` | Manual safety/stop path | Direct V2 `HassClient` path | HA/RD | RD6018 output | **MIGRATE to same V2 port; preserve containment priority** |
| `manual_mode.py` MAIN→MIX | `ManualPhaseLifecycle` | `ManualExecutionBoundary` with injected V2 owner | V2 physical owner | RD6018 setpoints | **KEEP as boundary shape; consolidate owner** |
| `runtime/output/bridge/PhysicalBridgeExecutor` | V3/output gate and lease | Its injected `PhysicalBridgeTransport` | arbitrary transport | physical target | **MIGRATE or quarantine; not a second owner** |
| `runtime/output/executor/*` command plans | output execution model | abstract/dry-run executor contracts | injected executor | none unless wired | **KEEP as contracts/simulation only** |
| `runtime/physical/connectors/ha_esp.py` | connector caller | connector itself | HA service API | RD6018 | **MIGRATE to adapter behind V2 owner** |
| `runtime/physical/connectors/esp_direct.py` | connector caller | connector itself | ESPHome API | RD6018 | **MIGRATE to adapter behind V2 owner or remove** |
| `runtime/physical/transports/*` | transport factory/caller | transport | HA/ESPHome API | RD6018 | **KEEP read-only; write methods migrate/quarantine** |
| `runtime/physical/commands/*` | command planner/verifier | no owner until wired | connector/transport | RD6018 | **KEEP contract/verification; no direct production owner** |
| `runtime/physical/lease/*` | bench/lease layer | lease provider | no hardware by itself | execution authorization | **KEEP only as contract; unify with V2 authority** |

## Manual canonical path

The target path is:

```text
Manual input/state
  -> ManualPhaseLifecycle
  -> ChargeDecision / ExecutionIntent
  -> Safety + approval/identity boundary
  -> one V2 execution port
  -> existing V2 physical owner
  -> HassClient / existing HA-RD adapter
  -> readback verification / audit
```

Specific actions:

- `safe_enable_output()` becomes a V2 owner operation invoked only through
  the approved execution port after identity, safety and readback checks.
- Normal `turn_off()` remains a safety-capable operation, but it must use the
  same owner/adapter boundary rather than a parallel direct caller.
- Exception shutdown keeps fail-closed priority and may bypass ordinary
  decision flow only through a documented containment operation owned by V2.
- MAIN→MIX target changes continue to originate in
  `ManualPhaseLifecycle`; the execution boundary translates and verifies them
  but never computes phase or targets.

## `runtime/output` disposition

### Can remain as contracts

- intent/value models;
- command-plan models;
- readback/result records;
- safety/verification interfaces;
- dry-run and shadow implementations;
- audit data structures.

### Must become adapters or be quarantined

- `PhysicalBridgeExecutor`;
- transport `apply()` calls;
- async `disable_output()` calls;
- controlled transition helpers;
- any lease provider that can authorize a production write.

These components may be retained only behind the single V2 execution port,
or clearly marked simulation/bench-only and unreachable from production
composition.

## `runtime/physical` disposition

### Retain as adapter/verification material

- read-only telemetry and readback transports;
- target validation and comparison models;
- verification evidence models;
- transport protocols with no production write authority.

### Migrate or remove from the independent execution surface

- HA/ESPHome connector write methods;
- independent output command entrypoints;
- independent physical lease ownership;
- bench executors reachable from production runtime.

The adapter must receive an approved execution request from the V2 owner and
return acceptance, readback, verification and failure results. It must not
select programs, decide phases, own sessions, or create a second lease.

## Consolidation phases

1. Freeze and inventory all V2 write entrypoints and safety containment paths.
2. Define one V2 execution port covering setpoints, output state, readback and
   verified OFF.
3. Route manual start, stop, error shutdown and MAIN→MIX through that port.
4. Mark `runtime/output` executor and `runtime/physical` write connectors as
   bench-only until routed behind the port.
5. Keep read-only transports available for observation, with no write methods
   exposed to domain code.
6. Add import/reachability tests proving one production execution owner.
7. Only after tests and review, consider a separate deployment change.

## Acceptance criteria

- one production writer/owner for RD6018 output and setpoints;
- no direct manual-mode writes outside the V2 execution port;
- V3 decisions produce intents only;
- adapter writes require approved identity/safety context;
- all writes have readback and audit correlation;
- emergency/verified-OFF containment remains fail-closed;
- physical connector code cannot be reached as a second owner;
- read-only observation remains available without write capability.

Final plan status: `READY_FOR_IMPLEMENTATION_REVIEW`

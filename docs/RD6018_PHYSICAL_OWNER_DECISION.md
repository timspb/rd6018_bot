# RD6018 Physical Execution Owner Decision

Status: `DECISION_RECORDED — OPTION_A_RECOMMENDED`

Scope: read-only analysis of the current `v3-full-migration-release` branch.
No code, deployment or hardware changes were made.

## Current component assessment

| Component | Can write hardware? | Owns execution decisions? | Requires V3 intent? | Bypasses ExecutionPort? | Migration disposition |
|---|---:|---:|---:|---:|---|
| `runtime/v2_runtime.py` | Yes | Yes, for existing V2 production flow | No, legacy V2 path | Yes, by design of current V2 owner | Keep as the temporary/approved physical owner |
| `runtime/v2_lifecycle.py` | Yes | Yes, lifecycle/transition path | No | Yes, through V2 owner internals | Keep under V2 owner; do not duplicate in V3 |
| `runtime/v2_startup_recovery.py` | Yes | Recovery execution decisions | No | Yes, through V2 owner internals | Keep as V2 recovery owner |
| `application/ExecutionPort` | Delegates writes to V2 owner | No | Yes | No | Keep as canonical V3-to-V2 boundary |
| `runtime/output/bridge/PhysicalBridgeExecutor` | Yes | Yes, command-plan execution | Uses output intent, not `ExecutionIntent` | Yes | Remove from production composition or reduce to simulation/verification |
| `runtime/physical/connectors/esp_direct.py` | Yes | No/adapter-level | No explicit V3 requirement | Yes if invoked directly | Keep only as an adapter behind the single owner |
| `runtime/physical/connectors/ha_esp.py` | Yes | No/adapter-level | No explicit V3 requirement | Yes if invoked directly | Keep only as an adapter behind the single owner |
| `runtime/physical/transports/ha102.py` | Yes for service calls | No/transport-level | No | Yes if invoked directly | Keep transport-only; no authority |
| `runtime/physical/transports/esp128.py` | Has controlled write surface | No/transport-level | No | Yes if invoked directly | Keep only for explicitly owned adapter/verification use |

The production entrypoint imports `runtime.v2_runtime`; the output/physical
trees are nevertheless write-capable and independently executable in the
branch. Their existence and tests prevent treating them as read-only by
default.

## Option A — V2 remains physical owner (recommended)

### Target

```text
V3 decision / ExecutionIntent
        |
        v
ExecutionPort
        |
        v
V2 physical owner
        |
        v
HA / ESPHome / Modbus adapters
        |
        v
RD6018
```

### Required changes

- Keep V2 guarded writes, verified OFF, readback and hardware safety as the
  only production physical authority.
- Keep `ExecutionPort` as the single V3-to-V2 request boundary.
- Convert `runtime/physical` connectors/transports into injected adapters with
  no ownership, lifecycle or decision authority.
- Retain readback, verification, simulation and evidence contracts.
- Remove or quarantine `PhysicalBridgeExecutor` and all independent output
  command execution from production composition.
- Route any required manual/operator setting changes through
  `ExecutionIntent -> ExecutionPort`.
- Preserve the existing managed-only lease semantics and local/autonomous
  independence.

### Impact

- Code impact: medium; mostly composition and adapter wiring plus focused
  removal/quarantine of duplicate executor paths.
- Risk: lowest; preserves the deployed V2 owner and node101 behavior.
- Compatibility: highest; existing V2/HassClient and rollback controls remain.
- node101 impact: none until a separately approved deployment; no ownership
  transfer is required.

## Option B — PhysicalBridgeExecutor becomes owner

### Target

```text
V3 decision / ExecutionIntent
        |
        v
PhysicalBridgeExecutor
        |
        v
HA / ESPHome / Modbus adapters
        |
        v
RD6018
```

### Required changes

- Transfer actuator authority from V2 runtime/HassClient to the bridge.
- Define one authoritative lease/ownership implementation and remove the V2
  competing write path.
- Port all V2 safety, verified-OFF, readback, recovery and emergency semantics
  into the bridge boundary.
- Make every START/STOP/setpoint operation carry session, trace, decision and
  approval identity.
- Rework startup recovery, manual mode, autonomous mode and rollback.
- Compile and bench-validate matching HA/ESPHome/Modbus contracts on node101
  before any deployment.
- Update the service composition and provide a verified rollback to V2.

### Impact

- Code impact: very high; it is an ownership migration, not a cleanup.
- Risk: high; changes actuator authority, lease behavior and recovery.
- Compatibility: low until the new owner is physically validated.
- node101 impact: mandatory deployment and hardware bench validation; not
  allowed as part of this release-preparation task.

## Decision

Choose **Option A**. It satisfies the current architecture rule with the
smallest physical risk and preserves node101 compatibility. Option B must be a
separate, explicitly approved ownership-migration program and must not be
smuggled into the current release.

Remaining release blockers under Option A:

1. Quarantine/remove the independent `runtime/output` executor path.
2. Prove all `runtime/physical` connectors are adapters only and cannot be
   invoked as owners.
3. Complete static reachability tests for `ExecutionPort` and V2-owner
   uniqueness.
4. Review safety/lease semantics against the current source-of-truth docs.

No merge, deployment, service restart, lease change or physical action was
performed.

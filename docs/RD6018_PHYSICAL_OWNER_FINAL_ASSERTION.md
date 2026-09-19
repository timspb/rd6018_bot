# RD6018 Physical Execution Owner — Final Assertion

Status: `PHYSICAL_OWNER_CONFIRMED`

Scope: read-only source inspection of the WS133 release working copy. No code,
runtime state, deployment, merge, or hardware state was changed.

## Write-capable surface inventory

| Component | `CAN_WRITE_HARDWARE` | Classification | Ownership authority |
|---|---:|---|---|
| `runtime/v2_runtime.py` and its V2 lifecycle/recovery helpers | true | Preserved V2 physical owner | Yes — sole production owner |
| V2 `HassClient`/safety-controlled actuator surface | true | Existing V2 adapter/guard used by the owner | No independent lifecycle authority |
| `application/execution_port.py` | not hardware-capable | V3-to-V2 execution boundary | No hardware ownership |
| `runtime/output/**` | false | Contracts, policy, simulation, readback/audit | No |
| `runtime/output/bridge/PhysicalBridgeExecutor` | false | Quarantined compatibility surface; all execution methods reject | No |
| `runtime/physical/connectors/**` | false | Read-only discovery, health, snapshot/readback surfaces | No |
| `runtime/physical/transports/**` | false | Read-only transport surfaces in this tree | No |
| `runtime/physical` contracts/verification/lease models | false | Models, validation, and verification | No |

The connector and transport write-shaped method names are compatibility
interfaces only. Their concrete implementations fail closed and contain no
HA service, ESPHome command, or transport write call.

## Canonical write chain

### V3 intent path

`V3 decision`
→ `Safety/approval boundary`
→ `ExecutionIntent`
→ `ExecutionPort`
→ `V2 physical owner`
→ `V2 HassClient/safety guard`
→ `existing HA/ESPHome/Modbus adapter`
→ `RD6018`
→ `readback/verification`

`ExecutionPort` calls only the injected V2 owner for enable, target changes,
and disable, and records the identity/audit result. It does not calculate
phase or targets.

### Preserved V2 path

`V2 runtime/lifecycle/recovery caller`
→ `V2 safety/ownership guard`
→ `V2 HassClient actuator method`
→ `existing adapter/transport`
→ `RD6018`
→ `readback/verification`

These are multiple V2 call sites inside one preserved owner family, not a
second ownership authority. They remain intentionally unchanged by WS133.

## Duplicate-owner check

- `PhysicalBridgeExecutor`: **not** an independent owner; write methods reject
  before transport access.
- `runtime/output/**`: no hardware write calls found.
- `runtime/physical/**`: no concrete hardware write calls found; read-only
  surfaces remain.
- `manual_mode.py`: no direct actuator calls found; manual operations use the
  intent/`ExecutionPort` boundary.
- `bot.py` and UI surfaces: no direct physical owner construction or hardware
  write path found in the checked sources.
- Autonomous execution decision: retained only in V2 production runtime;
  V3 does not autonomously execute.

Therefore there is one physical ownership authority: the V2 production
owner. There is no second component with both hardware write capability and
independent execution authority.

## Validation evidence

- WS135 inventory/source scan: PASS.
- WS133 ownership invariants: 3/3 PASS.
- Working-tree `git diff --check`: PASS.
- `compileall`: PASS.
- No hardware, deployment, service restart, or merge performed.

## Decision

`PHYSICAL_OWNER_CONFIRMED` — Option A is the confirmed model. The remaining
release-wide historical whitespace and full-suite environment blockers are
not ownership-model blockers and were not modified by this read-only audit.

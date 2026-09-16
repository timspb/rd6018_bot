# RD6018 Execution Path Migration Map

Status: `IMPLEMENTED_BOUNDARY / PHYSICAL_TREE_QUARANTINED`

| Operation | Decision source | Canonical boundary | Adapter/owner | Hardware |
|---|---|---|---|---|
| Manual start / `safe_enable_output` | manual operator intent + `ExecutionIntent` | `ExecutionPort.enable` | existing V2 owner / `HassClient.safe_enable_output` | RD6018 via HA |
| Manual MAIN→MIX setpoints | `ManualPhaseLifecycle` | `ExecutionPort.apply_intent` | existing V2 owner setters | RD6018 V/I |
| Manual stop | manual stop intent | `ExecutionPort.disable` | existing V2 owner / `HassClient.turn_off` | RD6018 output |
| Manual thermal/error shutdown | safety/containment intent | `ExecutionPort.disable` | existing V2 owner / verified OFF path | RD6018 output |
| V2 automatic setpoints | V2 controller | existing V2 runtime path | `HassClient` | RD6018 via HA |
| V2 startup recovery | V2 recovery owner | existing V2 runtime path | `HassClient` | RD6018 via HA |
| `runtime/output/**` writes | output executor | not production-wired | injected transport | quarantined |
| `runtime/physical/**` write connectors | connector caller | not production-wired | HA/ESPHome connector | quarantined |

## Invariant

The production path has one physical owner: V2. V3/manual lifecycle code may
create an `ExecutionIntent`, but it cannot select phases, call HA/ESPHome, or
invoke a physical connector directly.

## Quarantine rule

`runtime/output/**` and `runtime/physical/**` remain available for contracts,
read-only observation, verification, and simulation. Their write-capable
executor/connector surfaces are not part of production composition and must
not be imported by the production entrypoint.

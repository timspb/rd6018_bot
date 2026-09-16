# RD6018 Containment Ownership Model

Status: Phase 3.0 preparation. Read-only inventory plus an unconnected data
contract. No shutdown behavior is changed.

## Common result contract

`ContainmentResult` describes a containment request and its verification. It is
not an actuator command and is not connected to any current writer.

```text
trigger
  -> requested_action
  -> physical_owner
  -> verification_state
  -> final state
```

## Current containment owners

| Source/owner | Trigger | Requested action | Physical action | Verification method | Final state |
|---|---|---|---|---|---|
| `runtime/v2_runtime.py` soft watchdog | HA/runtime timeout | hard stop | V2 safety surface requests Output OFF | HA live/readback and controller/session state | stopped or containment |
| `runtime/v2_runtime.py` hardware watchdog | stale controller update, high voltage | emergency shutdown | V2 safety surface requests Output OFF | live switch/telemetry readback | stopped/diagnose |
| `runtime_safety.py` | invalid telemetry/readback/command precondition | fail closed | guarded OFF where required | raw live state and output evidence | failed/contained |
| `runtime_safety_v2.py` | OVP/OCP, temperature, external sensor integrity | ensure OFF and retire session | safety wrapper and verified OFF | output/readback plus durable latch where applicable | latched/contained |
| `runtime_safety_strict.py` | lease renewal or strict runtime failure | fail closed | OFF and lease disarm path | HA readback plus lease ACK | OFF confirmed or unconfirmed |
| `safe_output.py` | transactional enable/disable failure | force OFF | `SafeOutputCoordinator._force_off` | adapter result/readback | OFF confirmed/unconfirmed |
| `edge_safety_lease.py` | lease disarm/renewal failure | preserve fail-safe lease state | edge lease command; local edge protection remains authoritative | generation, armed/tripped state, fresh Modbus/readback | armed, disarmed, or contained |
| ESPHome dead-man | local lease expiry/watchdog | local Output OFF | ESPHome local physical action | edge-local state/readback | edge containment |
| `manual_mode.py` | operator stop, exception, thermal/session failure | stop session and OFF | composed safety/output surface | manual session state and output readback | stopped/cooling/failed |
| `manual_runtime_v2.py` | manual exception or containment | stop and contain | composed safety/output surface | session and output state | contained/failed |
| diagnostic/recovery paths | probe/restart/readback failure | restore safely or OFF | diagnostic/recovery adapter | positive OFF/readback | recovery blocked or contained |

## Verification vocabulary

| State | Meaning |
|---|---|
| `NOT_REQUESTED` | no physical containment request was made |
| `REQUESTED` | request was issued; evidence is incomplete |
| `OFF_CONFIRMED` | positive physical OFF evidence exists |
| `OFF_UNCONFIRMED` | OFF was requested but not positively established |
| `FAILED` | containment operation reported failure |
| `UNKNOWN` | source cannot establish the operation/evidence state |

`OFF_UNCONFIRMED` remains conservative containment. It must not be normalized
to success and must not silently reauthorize Output.

## Ownership conclusions

1. Runtime watchdogs and safety guards decide that containment is required.
2. `SafeOutputCoordinator` and the composed V2 safety surface mediate Python
   output operations.
3. `EdgeSafetyLease` and ESPHome retain independent edge/dead-man authority.
4. Manual runtime owns session lifecycle, not a second physical safety policy.
5. The Phase 3 contract must initially be an observation/result envelope only;
   connecting writers requires a separate parity and failure-containment review.


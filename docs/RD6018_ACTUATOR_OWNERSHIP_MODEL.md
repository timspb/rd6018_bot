# RD6018 Actuator Ownership Model

Status: Phase 4.0 preparation. Inventory, contracts and shadow mapping only.

No actuator operation is moved or executed by this document.

## Current actuator inventory

| Operation | Current caller | File/function | Trigger | Current owner | Reachability | Current verification |
|---|---|---|---|---|---|---|
| `OUTPUT_ON` / `turn_on` | V2 runtime action application | `runtime/v2_runtime.py` pause/custom/manual/recovery paths | operator/program action | V2 runtime safety surface | production reachable, guarded | HA readback and safety preconditions |
| `OUTPUT_ON` | Manual session | `manual_mode.py:start`, `_resume_after_cooling` | manual start/resume | Manual manager + SafeOutput path | production reachable | safe enable transaction/readback |
| `OUTPUT_ON` | START transaction | `v2_startup.py:start_profile_transactional`, `v2_mix_mode.py` | approved V2 start | V2 transaction owner | production reachable through V2 | transactional enable/readback |
| `OUTPUT_OFF` / `turn_off` | Watchdogs | `runtime/v2_runtime.py:_hard_stop_charge`, `soft_watchdog_loop`, `watchdog_loop` | timeout/high voltage | V2 watchdog + safety | production reachable | live/readback and containment state |
| `OUTPUT_OFF` | Manual/session | `manual_mode.py:stop`, `manual_runtime_v2.py:stop` | operator stop/error | Manual manager + safety | production reachable | output readback/session state |
| `OUTPUT_OFF` | Safety containment | `runtime_safety.py`, `runtime_safety_v2.py`, `runtime_safety_strict.py` | telemetry/readback/thermal/lease fault | runtime safety | production reachable | positive OFF where available |
| `OUTPUT_OFF` | Safe output failure | `safe_output.py:_force_off` | transaction failure | SafeOutputCoordinator | production reachable | adapter/readback |
| `SET_VOLTAGE` | V2 action executor | `runtime/v2_runtime.py` | controller action | V2 runtime safety surface | production reachable, guarded | setpoint/readback and envelope checks |
| `SET_VOLTAGE` | Diagnostic/strict precondition | `diagnostic_probe.py`, `runtime_safety_strict.py` | probe or transition | safety/diagnostic boundary | guarded/bench-dependent | measured settle/readback |
| `SET_CURRENT` | V2 action executor | `runtime/v2_runtime.py` | controller action | V2 runtime safety surface | production reachable, guarded | setpoint/readback and envelope checks |
| `SET_CURRENT` | Diagnostic/strict precondition | `diagnostic_probe.py`, `runtime_safety_strict.py` | probe or transition | safety/diagnostic boundary | guarded/bench-dependent | measured settle/readback |

## Classification

### KEEP

- V2 transaction owner and current safety/output boundary;
- `SafeOutputCoordinator` as the intended transactional boundary;
- `EdgeSafetyLease`/ESPHome as independent physical dead-man authority;
- manual and diagnostic safety checks until parity is proven.

### DEPRECATE

- direct legacy UI/runtime actuator call sites;
- duplicate V2 wrappers that bypass a future common intent boundary;
- compatibility adapters once all callers use the reviewed contract.

### BLOCKED

- any UI -> HA/physical call;
- any V3 module importing actuator implementations;
- any new caller bypassing V2 safety/output ownership;
- any attempt to deduplicate or suppress a safety action before containment parity
  and bench evidence.

## Shadow contract

```text
ExistingActuatorRequest
          |
          v
map_existing_request()
          |
          v
ActuatorIntent
```

`ActuatorIntent` is data-only. It does not call HA, ESPHome, controller, FSM,
SafetySupervisor, SafeOutputCoordinator or a physical adapter.


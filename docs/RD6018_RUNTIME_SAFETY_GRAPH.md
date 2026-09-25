# RD6018 Runtime Safety Graph

Status: Phase 2.5 read-only characterization. This graph documents current
owners; it does not authorize a safety-policy change.

## Current high-level graph

```text
HA/ESP telemetry
      |
      v
data_logger / watchdog / safety guards
      |
      +--> controller/session stop decision
      |
      v
SafeOutputCoordinator / runtime safety wrappers
      |
      v
HassClient physical adapter
      |
      +--> RD6018 Output/setpoints
      +--> EdgeSafetyLease
                         |
                         v
                 ESPHome local dead-man
```

## Failure paths

| Trigger | Caller/function | Action | Current owner | Final boundary |
|---|---|---|---|---|
| HA telemetry exception | `runtime/v2_runtime.py:data_logger` | records loss/recovery state; current recovery window may defer stop | V2 runtime + recovery window | `SafeOutputCoordinator` / V2 safety |
| HA loss timeout | `soft_watchdog_loop`, `watchdog_loop` | `_hard_stop_charge()` and session/controller stop | V2 watchdog | `hass.turn_off` through safety surface |
| High voltage watchdog | `runtime/v2_runtime.py:watchdog_loop` | emergency stop, sets HV disconnect marker | V2 watchdog/controller | verified Output OFF path |
| Lease renewal failure | `runtime_safety_strict.py:get_all_live` -> `_renew_edge_lease_or_fail` | fail closed and ensure OFF | strict runtime safety | `EdgeSafetyLease` + safe OFF |
| Lease expiry | ESPHome lease package | local Output OFF/dead-man containment | ESPHome edge | physical edge output control |
| Output/readback failure | `hass_api.py`, `runtime_safety.py`, `safe_output.py` | fail closed, verify OFF, retain uncertainty if needed | SafeOutput/runtime safety | `HassClient.turn_off` + readback |
| Hardware OVP/OCP trip | `runtime_safety_v2.py:get_all_live` | `_ensure_output_off` | V2 runtime safety | Safe output boundary |
| PSU/external temperature fault | `runtime_safety_v2.py:_trip_external_temp_integrity` | OFF, retire session, latch fault | V2 safety | safe OFF + durable latch |
| Manual stop | `manual_mode.py:stop`, `manual_runtime_v2.py:stop` | stop session, turn OFF, confirm | Manual session manager | V2 safety/output surface |
| Emergency operator stop | legacy UI/runtime stop handlers | `_hard_stop_charge` or managed stop route | V2 runtime/operator guard | verified OFF boundary |

## Safety state observations

- The Python watchdog and runtime safety layers can both request containment.
- `SafeOutputCoordinator` is the transactional output boundary, but legacy V2
  paths still call the composed safety surface directly.
- `EdgeSafetyLease` is a separate physical dead-man authority; it is not a
  replacement for Python session/FSM ownership.
- OFF confirmation and lease disarm are coupled only after positive OFF
  confirmation. An unconfirmed OFF must remain contained.
- Current HA degradation/recovery state is an additional observation layer; it
  must not silently become a new actuator owner.

## Controller and session ownership

```text
Telegram/UI intent
  -> V2 route / manual manager
  -> ChargeControllerV2 or ManualSessionManager
  -> FSM/session mutation
  -> action/transaction decision
  -> V2 safety/output boundary
```

V3 preflight/plan/trace remains outside this graph's physical execution owner.


# RD6018 Actuator Intent Mapping

Status: Phase 4.1 shadow mapping only.

This document proves that existing actuator operations can be represented by
`ActuatorIntent` without changing their execution or ownership.

## Mapping inventory

| Current operation | Caller | Owner | Trigger | Reason/target | Intent operation/source/owner |
|---|---|---|---|---|---|
| OUTPUT_ON | `runtime/v2_runtime.py` | V2 safety surface | program/manual/recovery action | guarded enable / RD6018 Output | OUTPUT_ON / runtime path / V2 safety |
| OUTPUT_ON | `manual_mode.py:start` | Manual + SafeOutput | manual start | approved session / RD6018 Output | OUTPUT_ON / manual path / Manual owner |
| OUTPUT_ON | `manual_mode.py:_resume_after_cooling` | Manual + SafeOutput | cooling recovery | guarded resume / RD6018 Output | OUTPUT_ON / manual path / Manual owner |
| OUTPUT_ON | `v2_startup.py:start_profile_transactional` | V2 transaction | approved START | enable transaction / RD6018 Output | OUTPUT_ON / V2 transaction / V2 owner |
| OUTPUT_ON | `v2_mix_mode.py:start_mix_transactional` | V2 transaction | Mix transition | enable Mix / RD6018 Output | OUTPUT_ON / V2 Mix / V2 owner |
| OUTPUT_OFF | `runtime/v2_runtime.py:_hard_stop_charge` | V2 watchdog/safety | timeout/high voltage | contain active output / RD6018 Output | OUTPUT_OFF / watchdog / V2 safety |
| OUTPUT_OFF | `manual_mode.py:stop` | Manual + safety | operator/session failure | stop manual output / RD6018 Output | OUTPUT_OFF / manual / Manual owner |
| OUTPUT_OFF | `manual_runtime_v2.py:_contain_enable_exception` | Manual safety | enable exception | contain failed enable / RD6018 Output | OUTPUT_OFF / manual runtime / Manual safety |
| OUTPUT_OFF | `safe_output.py:_force_off` | SafeOutputCoordinator | transaction failure | force verified OFF / RD6018 Output | OUTPUT_OFF / SafeOutput / SafeOutput owner |
| SET_VOLTAGE | V2 runtime action executor | V2 safety surface | controller action | guarded voltage / voltage setpoint | SET_VOLTAGE / V2 runtime / V2 safety |
| SET_VOLTAGE | `diagnostic_probe.py` | diagnostic boundary | controlled probe | temporary diagnostic voltage / voltage setpoint | SET_VOLTAGE / diagnostics / diagnostic owner |
| SET_CURRENT | V2 runtime action executor | V2 safety surface | controller action | guarded current / current setpoint | SET_CURRENT / V2 runtime / V2 safety |
| SET_CURRENT | `diagnostic_probe.py` | diagnostic boundary | controlled probe | temporary diagnostic current / current setpoint | SET_CURRENT / diagnostics / diagnostic owner |

## Classification

### KEEP

Current V2 transaction, Manual, watchdog, safety and SafeOutput owners. They
remain authoritative until a separately reviewed execution-port migration.

### DEPRECATE

Diagnostic and legacy direct call-site representations that should eventually
be normalized behind the common intent/port boundary. Deprecation does not
remove their safety checks.

### BLOCKED

- UI-created physical intents;
- V3 modules importing actuator implementations;
- any mapper that executes the mapped request;
- any bypass of V2 safety/output ownership;
- any unknown operation fallback.

## Side-effect boundary

```text
existing path description
          |
          v
observe_actuator_path()
          |
          v
ActuatorIntent (data only)
```

The mapper does not call HA, ESPHome, controller, FSM, SafetySupervisor,
SafeOutputCoordinator or physical adapters.


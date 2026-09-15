# RD6018 Actuator Reachability Map

Status: Phase 2.5 read-only characterization.

## Actuator paths

| Operation | Source/caller | Production reachable | Current owner/final boundary |
|---|---|---:|---|
| `turn_on` | `runtime/v2_runtime.py` pause, custom/manual and recovery paths | Yes, guarded | `RuntimeSafetyGuard` -> `SafeOutputCoordinator`/`HassClient` |
| `turn_on` | `manual_mode.py:start`, `manual_mode.py:_resume_after_cooling` | Yes | `SafeOutputCoordinator.safe_enable_output` |
| `turn_on` | `v2_startup.py:start_profile_transactional`, `v2_mix_mode.py` | Yes through V2 transaction | V2 transaction owner -> safety/output |
| `turn_off` | `runtime/v2_runtime.py:_hard_stop_charge`, watchdog/data logger | Yes | V2 containment -> safety/output |
| `turn_off` | `manual_mode.py`, `manual_runtime_v2.py` | Yes | Manual manager -> safety/output |
| `turn_off` | `safe_output.py:_force_off`, recovery/diagnostic paths | Yes | `SafeOutputCoordinator` |
| `set_voltage` | `runtime/v2_runtime.py` action application | Yes | V2 runtime safety wrapper -> HA adapter |
| `set_voltage` | diagnostic probe and strict safety preconditioning | Bench/production guarded | safety wrapper; no UI ownership |
| `set_current` | `runtime/v2_runtime.py` action application | Yes | V2 runtime safety wrapper -> HA adapter |
| `set_current` | diagnostic probe and strict safety preconditioning | Bench/production guarded | safety wrapper |
| `controller.start()` | `ChargeControllerV2`, production controller composition | Yes | V2 controller/FSM owner |
| `controller.stop()` | controller guardrails, safety and manual stop paths | Yes | V2 controller/session owner |

## Non-production/bench surfaces

`physical_test_control*.py`, `runtime/physical/*` and
`runtime/output/bridge/*` are physical-capable surfaces. They are not the
current production execution owner, but their import/reachability surface must
remain statically isolated from V3/UI composition.

## Ownership conclusion

There is currently one intended production execution authority — the V2
composition — but several historical call sites reach its safety-wrapped
actuator surface. The safe cleanup order is inventory -> static guard -> common
execution port; deleting call sites before parity and rollback evidence would
be unsafe.


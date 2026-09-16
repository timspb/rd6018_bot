# RD6018 Containment Observation Mapping

Status: Phase 3.1 observation-only mapping.

This document maps current shutdown/containment paths to the Phase 3
`ContainmentResult` contract. It does not replace existing calls, alter
timeouts, change lease behavior, or change OFF semantics.

| Current path | Trigger | Source | Current action | Current verification | New requested action | Physical owner | New verification |
|---|---|---|---|---|---|---|---|
| Runtime watchdog HA timeout | stale HA/controller update | `runtime_watchdog` | `_hard_stop_charge` | live/readback + controller/session | verified output OFF | V2 safety/output | REQUESTED |
| Runtime watchdog high voltage | high voltage timeout | `runtime_watchdog` | hard stop + HV marker | HA live/readback | verified output OFF | V2 safety/output | REQUESTED |
| Runtime safety fail-closed | invalid telemetry/readback/precondition | `runtime_safety` | fail closed | raw live/output evidence | fail closed | runtime safety guard | UNKNOWN |
| Runtime safety V2 hardware/integrity | OVP/OCP/temp/sensor fault | `runtime_safety_v2` | ensure OFF + retire/latch | readback + latch | verified OFF and contain | V2 safety | UNKNOWN |
| Runtime safety strict lease failure | lease renewal/runtime failure | `runtime_safety_strict` | fail closed + lease handling | readback + lease ACK | verified OFF and lease contain | strict safety + edge lease | UNKNOWN |
| SafeOutput failure | transaction/post-enable failure | `safe_output_coordinator` | force OFF | adapter/readback | force verified OFF | SafeOutputCoordinator | UNKNOWN |
| Edge lease failure | renewal/disarm ACK failure | `edge_safety_lease` | preserve fail-safe lease | generation/edge readback | preserve edge containment | EdgeSafetyLease | OFF_UNCONFIRMED |
| ESPHome dead-man | local lease expiry | `esphome_dead_man` | local Output OFF | edge-local state | local Output OFF | ESPHome edge | UNKNOWN |
| Manual stop | operator stop/session failure | `manual_runtime` | stop + request OFF | session/readback | stop and verified OFF | Manual/V2 safety | REQUESTED |
| Emergency stop | explicit emergency request | `operator_emergency_stop` | hard/managed stop | positive OFF evidence | emergency verified OFF | V2 safety/output | REQUESTED |

## Mapping rules

1. `ContainmentResult` is an observation/result envelope, not a command.
2. `REQUESTED` is not equivalent to `OFF_CONFIRMED`.
3. `OFF_UNCONFIRMED` remains conservative containment.
4. `UNKNOWN` means the current path does not expose enough evidence to infer a
   stronger state without changing runtime behavior.
5. Existing owners remain authoritative until a separate migration is
   reviewed, tested and bench-validated.


# RD6018 node104 — ESP Native optional-status acceptance (read-only)

## Observation and safeguards — 2026-11-09 14:50:46 UTC

The original user report showed `control_output`, `take_ok`, `take_out`, `boot_power` as `unknown` in the installed bot's Native snapshot. On HOME-PC, commit `e99d434` fixed the ESP128 source adapter to expect native `SwitchInfo` for `control_output` and `BinarySensorInfo` for the other three fields. Source-only ESP/safety regression: **191 PASS, 0 FAIL**, exit 0.

Read-only inspection performed over the existing node104 pinned ED25519 SSH profile using its original secrets file; no secrets were printed. Remote commands loaded only installed bot configuration and opened a short-lived ESPHome Native subscription. Verified device identity: `timspb.rd6018-pb-recovery-v2`, firmware `2.3-ha-canonical`. No `switch_command`, button command, number command, lease action, START/OFF, state write, firmware upload, restart or physical output action.

## Actual native inventory and latest typed callback

| Logical key | ESP object_id | Info type | Native key | device_id | Typed callback | Age |
|---|---|---|---:|---:|---|---:|
| `control_output` | `output` | `SwitchInfo` | 1234004678 | 0 | `SwitchState(False)` | ~0.41 s |
| `take_ok` | `take_ok_v2` | `BinarySensorInfo` | 1057753628 | 0 | `BinarySensorState(True)` | ~0.46 s |
| `take_out` | `take_out_v2` | `BinarySensorInfo` | 726636468 | 0 | `BinarySensorState(False)` | ~0.46 s |
| `boot_power` | `boot_power_v2` | `BinarySensorInfo` | 164154738 | 0 | `BinarySensorState(False)` | ~0.46 s |
| `output_state` | `output_state_code_v2` | `SensorInfo` | 2040224759 | 0 | `SensorState(0.0)` | ~0.46 s |

The installed adapter's ordinary `get_live_values()` returned `None/unknown` with no typed callback provenance for the four optional fields despite each object appearing exactly once in inventory. The same connected transport's existing `_read_subscribed_state(object_id, expected_type)`, called with the correct expected types strictly **read-only**, returned all four values `status=ok`, the same inventory key/device_id, and fresh `SwitchState`/`BinarySensorState` callbacks.

This independently isolates the installed type-selection bug and excludes missing firmware objects or a general Native subscription failure for these four fields. The physical R18 reading is separate and authoritative for output state; it was `0.0/OFF` in this inspection. `control_output=False` is only the commanded switch surface and must not be substituted for R18. `take_ok=True` is diagnostic; `take_out=False` and `boot_power=False` are actual hardware configuration observations, not assumptions. Existing safety preflight still rejects a confirmed true `take_out` or `boot_power`.

## Acceptance and next action

**Physical read-only diagnostic PASS** for Native inventory, types and fresh values. **Installed application projection FAIL** because the deployed adapter still uses the old mapping. Source code `e99d434` is locally tested but not deployed. No firmware change is needed to correct this observed type mismatch. Add the small code fix to the next separately authorized node104 release, preserving the established staged versioning and physical acceptance procedure. Following installation, repeat the exact read-only check through normal `get_live_values()` and compare four fields against typed callbacks and independent R18. Do not claim full charge/session or Storage activation acceptance from this diagnostic; those are separate gates.

The remote single-use inspection scripts remain in ignored `.recipe-studio-local` on HOME-PC. No GitHub push, production session or actuator mutation was performed.

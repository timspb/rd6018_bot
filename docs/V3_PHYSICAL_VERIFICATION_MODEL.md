# V3 two-phase physical verification

Physical execution is not successful merely because a command was sent. The
only acceptable result is:

```text
pre-readback MATCH
  -> manually authorized action
  -> post-readback MATCH
  -> confirmed evidence
```

`PhysicalVerificationService` is a verification-only domain service. It does
not create commands, call HA/ESPHome, mutate a lease or operate Output. It
uses the existing immutable `HardwareSnapshot`; no second physical-state
format is introduced.

## Required order

```text
Safety -> envelope -> bench lease -> pre-readback -> compare
  -> manual ExecutionGate -> action -> post-readback -> compare -> audit
```

Any missing snapshot, stale timestamp, missing required field, transport error
or value outside tolerance is fail-closed. There is no automatic retry.

For `DISABLE_OUTPUT`, the postcondition is explicitly `output_state == OFF`
and `measured_current == 0`. The first physical write phase does not enable
Output, change V/I, or reset OVP/OCP.

## Comparison parameters

The tolerances are configuration data in `config/runtime/runtime.yaml`:

| Parameter | Current configured value |
|---|---:|
| `verification_voltage_tolerance_v` | `0.01 V` |
| `verification_current_tolerance_a` | `0.05 A` |
| `verification_protection_tolerance` | `0.05` |
| `snapshot_timestamp_tolerance_s` | `10 s` |

They are not embedded in the strategy or transport. The evidence model keeps
before snapshot, requested state, write result, pre-readback/comparison,
action, post-readback/comparison and final result together.

## Current boundary

The verification service is available for the future physical executor, but it
is not wired into production runtime. Automatic execution remains disabled;
the real bench path still requires a real operator, a valid
`DISABLE_OUTPUT_ONLY` bench lease and explicit gate ARM.

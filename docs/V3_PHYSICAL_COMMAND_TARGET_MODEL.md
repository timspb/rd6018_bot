# V3 physical command targets

This phase defines a target-and-readback contract without connecting command
execution to production. A command is represented by its requested values and
the state that must be observed afterward; delivery alone is never success.

Supported preparation targets are `SET_VOLTAGE`, `SET_CURRENT`,
`RESET_PROTECTION` and `DISABLE_OUTPUT`. `ENABLE` is deliberately absent from
the model. No target in this phase calls HA, ESPHome or RD.

## Verification flow

```text
V3 intent -> safety -> envelope -> bench lease -> connector
  -> write (future connector implementation)
  -> fresh snapshot -> expected readback comparison -> evidence
```

`HAESPConnector` and `ESPDirectConnector` remain independent. The same target
can be verified through both and compared, but one connector is never a
required intermediate hop for the other. Missing or stale readback is a
failure.

## Target fields

`PhysicalCommandTarget` contains `command`, `requested_values`,
`expected_readback`, per-field `tolerance` and `timestamp`. Readback aliases
such as `current_setpoint` and `voltage_setpoint` map only to fields of the
existing `HardwareSnapshot`; no second physical-state model is introduced.

Tolerance values are supplied by configuration at the caller boundary (the
current verification tolerances are in `config/runtime/runtime.yaml`). They
are not embedded in command or connector logic.

## Current status

This is a preparation and comparison contract. No SET, RESET or ENABLE command
was sent during this phase, and automatic connector switching remains off.

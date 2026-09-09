# RD Autonomous Operation Boundary

## Purpose

Separate physical RD6018 safety from application ownership.

`AUTONOMOUS` does not mean autonomous Pb charging. It means the RD6018 may be used as a general-purpose programmable power supply without a permanently available bot/HA control plane.

## Concepts

### Ownership

Who may issue application-level actuator commands:

- `BOT_MANAGED`
  - bot owns charge/application control
  - recipes, sessions and restore are allowed
- `EXTERNAL`
  - external operator/application owns setpoints
  - bot does not run application control

`HANDS_OFF` is the existing ownership-transfer workflow. It is not evidence that
the edge is in `AUTONOMOUS`; the explicit persistent edge autonomous authority must
be observed separately.

### Operation mode

What type of operation is expected:

- `MANAGED`
  - requires the application control plane
  - existing Pb controller semantics remain
- `AUTONOMOUS`
  - no dependency on Telegram, HA heartbeat or charge session
  - RD hardware safety remains active

## Always active safety

Regardless of operation mode:

- PSU internal temperature protection
- absolute voltage limits
- absolute current limits
- power/thermal limits
- hardware fault handling

## Managed-only policies

These must not terminate autonomous operation:

- missing Wi-Fi
- missing Telegram
- missing charge session
- missing Pb chemistry profile
- missing external battery temperature
- lease renewal timeout

## External temperature

`temp_ext` is application-specific:

- Pb charging may require it.
- General PSU autonomous operation must not require it.

Internal PSU protection remains mandatory.

## Migration rule

Do not disable safety. Move ownership and application policy out of the hardware safety layer.

# RD6018 Control dashboard

The versioned source is [`rd6018_control.yaml`](rd6018_control.yaml). It uses
Home Assistant Sections layout and stock cards only. The dashboard is a
read-only display: it contains no `switch` or `number` control entities and no
service actions. Tile taps open More Info.

## Live installation

- Home Assistant: `http://192.168.1.102:8123/rd6018-control`
- Dashboard title: `RD6018 Control`
- URL path: `rd6018-control`
- Installed through the authenticated Home Assistant WebSocket dashboard API.
- The existing `dashboard-rd6018` dashboard was read before installation and
  left intact.
- The dashboard uses only built-in frontend cards; no frontend resource or
  HACS dependency is required.

To compare or restore the dashboard configuration, open the YAML file and use
the dashboard raw configuration editor. If recreating it, first add a new
dashboard with URL path `rd6018-control`, then paste the YAML configuration.
Do not overwrite `dashboard-rd6018`.

## Entity mapping and interpretation

Live HA state metadata on 2026-11-05 confirmed the entity IDs used here.
Measured battery voltage is `sensor.rd_6018_battery_voltage`; measured output
current is `sensor.rd_6018_output_current`. The similarly named
`number.rd_6018_output_current` is a writable setpoint and is deliberately not
used. Setpoint/protection tiles use the separate readback sensors:

- Vset / Iset: `sensor.rd6018_rd_6018_set_voltage_readback_v2` and
  `sensor.rd6018_rd_6018_set_current_readback_v2`.
- OVP / OCP: `sensor.rd6018_rd_6018_ovp_readback_v2` and
  `sensor.rd6018_rd_6018_ocp_readback_v2`.
- CV / CC: `binary_sensor.rd_6018_constant_voltage` and
  `binary_sensor.rd_6018_constant_current`.
- Output is shown as the read-only numeric register mirror
  `sensor.rd6018_rd_6018_output_state_code_v2`, never as the output switch.
- Protection code and lease, quarantine, autonomous and communication-age
  values are informational HA entities.

The history graph shows Recorder history for measured battery voltage and
measured output current over 24 hours. HA is a secondary display path. Its
states, history and this dashboard are not direct ESP Native API evidence and
must not be used to claim physical Output status or authorize charging,
ownership, deployment or safety decisions. Before any such check, follow
[`ESP_NATIVE_LIVE_EVIDENCE.md`](../../ESP_NATIVE_LIVE_EVIDENCE.md) and obtain
fresh typed callbacks directly from the ESP.

## Verification record

HA version reported `2026.10.4`. The `/api/config`, `/api/states`, dashboard
list, existing RD6018 dashboard config, frontend resources and 24-hour
Recorder history were queried read-only. Stock frontend resources were
available; the live RD6018 dashboard used Sections layout. The new dashboard
was saved and read back through the dashboard WebSocket API. No physical
output, setpoint, lease, battery, service or firmware command was sent.

Direct ESP Native API access was blocked during this task because the existing
local ESPHome encryption key was unavailable. HA showed Output ON at the time
of inspection; this is only a secondary HA observation, not physical
verification. No output operation was attempted.

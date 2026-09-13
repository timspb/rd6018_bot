# V3 independent physical connectors

V3 has two independent paths to the same RD6018:

```text
V3 -> HAESPConnector -> HA 192.168.1.102 -> ESPHome -> RD6018
V3 -> ESPDirectConnector -> ESPHome 192.168.1.28 -> RD6018
```

They are alternatives, not sequential links. A failure in one connector must
not mutate or invalidate the other connector's lifecycle. Automatic fallback
and automatic connector selection are intentionally absent.

## Configuration and access order

Connector selection is described in `config/physical/connectors.yaml`; the
path profiles are `config/physical/ha_esp.yaml` and
`config/physical/esp_direct.yaml`. Endpoint, entity and secret references stay
in the underlying canonical `ha102.yaml` and `esp128.yaml` transport profiles.

For a read-only check: load validated config, explicitly create one connector,
run `discover()`, `get_snapshot()`, `get_capabilities()` and `health_check()`,
then close it. Create the other connector independently and repeat. Compare
only completed snapshots using configured voltage/current/timestamp tolerances.

## Current write boundary

Both connectors expose only discovery, health, snapshot and capabilities in
this phase. Physical writes remain behind the existing manual bench lease,
two-phase verification and `PhysicalExecutionGate`; no connector is wired to
automatic runtime fallback or production execution.

The first live read-only run passed for both paths; evidence is recorded in
`docs/V3_INDEPENDENT_CONNECTORS_EVIDENCE_2026-09-13.md`. The next physical
write must still use the separate verified-off lease and two-phase verification
gate.

The first controlled physical execution was completed independently through
both connectors using `DISABLE_OUTPUT` only. The pre/post evidence is in
`docs/V3_FIRST_PHYSICAL_EXECUTION_EVIDENCE_2026-09-13.md`; no setpoint, reset or
enable command was executed.

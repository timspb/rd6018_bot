# V3 live read-only transport smoke test

`LiveSmokeRunner` loads the validated config, creates `HA102Transport` and
`ESPHomeTransport`, performs discovery, read-only snapshot, capability read
and health check, then closes both connections and records
`PhysicalSnapshotEvidence`.

No executor, gate arm, service call, Output command, setpoint write or reset
method is reachable from this runner. A run is valid only when both snapshots
are connected and the comparison is not `INCONCLUSIVE`; small numeric
differences are accepted using the configured tolerances in
`config/runtime/runtime.yaml`. Timestamp freshness is also part of comparison.

This smoke test is evidence collection, not a bench charge or production
activation. A later physical bench run must separately use the manual
execution gate and verified-OFF protocol.

## Access map and run order

The canonical access parameters are kept here, not in Python code:

| Source | Endpoint | Config | Secret reference |
|---|---|---|---|
| HA102 | `192.168.1.102:8123` | `config/physical/ha102.yaml` | env `HA_TOKEN` |
| ESP128 | `192.168.1.28:6053` | `config/physical/esp128.yaml` | env `ESPHOME_API_KEY` |

The repository stores only secret names. In the current deployment, the
operator loads `HA_TOKEN` from the node-101 runtime environment and
`ESPHOME_API_KEY` from the Home Assistant ESPHome secrets file
`/config/esphome/secrets.yaml`; values must never be copied into Git,
documentation or command output. If these locations change, update the
deployment/runbook source rather than the transport code.

Repeatable read-only order:

1. Load `config/` through the validated runtime config loader.
2. Confirm physical execution is disabled and both transports are read-only.
3. Create `HA102Transport`; discover, read snapshot, read capabilities and run
   health check; close the transport.
4. Create `ESPHomeTransport`; connect with the encrypted API, discover, read
   snapshot, read capabilities and run health check; close the transport.
5. Compare snapshots using the tolerances in `config/runtime/runtime.yaml`.
6. Save `PhysicalSnapshotEvidence` with timestamp and operator/source.

The ESPHome object mapping belongs exclusively in
`config/physical/esp128.yaml`; HA entity mapping belongs exclusively in
`config/physical/ha102.yaml`. If a firmware or HA entity is renamed, change
the mapping there and rerun the read-only smoke test. Never infer a write path
from a successful read.

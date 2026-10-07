# V3 live read-only transport smoke test

`LiveSmokeRunner` loads the validated config, creates `HA102Transport` and
`ESPHomeTransport`, performs discovery, read-only snapshot, capability read
and health check, then closes both connections and records
`PhysicalSnapshotEvidence`.

No executor, gate arm, service call, Output command, setpoint write or reset
method is reachable from this runner; the runner is strictly read-only. A run
is valid only when both snapshots are connected and the comparison is not
`INCONCLUSIVE`; small numeric
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
operator loads `HA_TOKEN` from the node-104 runtime environment and
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


## Operator CLI

Use the strictly read-only wrapper:

```text
python tools/live_physical_smoke.py --operator <label>
```

The command returns exit code `0` only when both transports produce valid
snapshots and their comparison is `MATCH`. Configuration, credential,
connectivity or snapshot failures return `BLOCKED` with exit code `2`.
The JSON output contains no credential values and does not expose a physical
write operation.

2026-10-07 HOME-PC preflight: HA102 TCP/8123 reachable; ESP128 TCP/6053 not
reachable; required live environment values absent. Result: `BLOCKED`; no
physical command sent.


## 2026-10-07 fail-closed snapshot-validity correction

Fresh read-only evidence exposed a validity defect in the original smoke runner.
`HA102Transport` could return `connection_state=connected` while every required
RD6018 entity state was `unavailable`; the runner previously classified that
snapshot as `VALID` using connection state alone.

Root cause: snapshot quality did not require the bench-critical readback fields.
Impact: two connected but incomplete sources could be misrepresented as usable
smoke evidence. No physical command was involved.

The canonical runner now requires non-null Output, measured V/I, configured V/I,
OVP, OCP, temperature and battery voltage before a transport run is `VALID`.
Missing fields produce `INVALID` with an explicit `missing_fields` reason.

Fresh HOME-PC evidence after the correction:
- HA API authentication: PASS (`HTTP 200`);
- all configured RD6018 HA entity IDs exist, but their current state is
  `unavailable`;
- configured ESP static IP remains `192.168.1.28`;
- ESP ping and TCP/80, TCP/443, TCP/6053: unavailable from HOME-PC;
- smoke result: `BLOCKED` (`HA102=INVALID`, `ESP128=ERROR`);
- Output/setpoints/protection/RD writes: none.

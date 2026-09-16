# V3 independent connector read-only evidence

Status: `PASS`

| Connector | Discovery | Health | Output | V | I | Set V | Set I | OVP | OCP | Temperature |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `ha_esp` | 9 entities | connected | OFF | 0.00 | 0.00 | 13.94 | 0.55 | 16.70 | 12.00 | 31 |
| `esp_direct` | 66 entities | connected | OFF | 0.00 | 0.00 | 13.94 | 0.55 | 16.70 | 12.00 | 31 |

The run used independent connector lifecycles and read-only methods only:
`discover`, `get_snapshot` and `health_check`. No enable, disable, setpoint,
reset, lease or production-runtime action was executed.

Cross-connector snapshot comparison: `MATCH` under the configured voltage,
current and timestamp tolerances. Secret values are intentionally excluded.

The HA path used the configured `switch.rd_6018_output` only as a discovered
control mapping; this read-only run did not call it.

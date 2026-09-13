# V3 first controlled physical execution evidence

Status: `PASS`

Runtime branch: `codex/v3-runtime-consolidation`

| Connector | Start (UTC) | Health | Lease/gate | Command | Pre | Post | Target |
|---|---|---|---|---|---|---|---|
| `ha_esp` | `2026-09-13 16:48:05Z` | connected | valid/manual | `DISABLE_OUTPUT` | MATCH | MATCH | MATCH |
| `esp_direct` | `2026-09-13 16:48:06Z` | connected | valid/manual | `DISABLE_OUTPUT` | MATCH | MATCH | MATCH |

Both paths were executed separately. No automatic connector switching was
used. The selected connector sent only `DISABLE_OUTPUT`; each run then read a
fresh snapshot and verified the result.

## Readback

| Connector | Before Output | Before I | After Output | After I | Set V | Set I | OVP | OCP | Temperature |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ha_esp` | OFF | 0.00 A | OFF | 0.00 A | 13.94 V | 0.55 A | 16.70 V | 12.00 A | 31 C |
| `esp_direct` | OFF | 0.00 A | OFF | 0.00 A | 13.94 V | 0.55 A | 16.70 V | 12.00 A | 31 C |

The command was accepted by the selected transport and the expected
hardware state was confirmed by post-readback. Both connectors independently
reported `MATCH` against the command target.

No `ENABLE`, `SET_VOLTAGE`, `SET_CURRENT`, `RESET_PROTECTION` or charge start
was executed. Secret values are excluded.

Next gate: separate setpoint-write validation. It is not implied by this
verified-off result.

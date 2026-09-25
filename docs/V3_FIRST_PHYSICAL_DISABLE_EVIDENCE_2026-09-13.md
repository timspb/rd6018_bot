# V3 first physical disable evidence

Status: `PASS`

| Field | Evidence |
|---|---|
| Requested baseline | `b0d9fb46a8caf753e9a1f55e8f07b90eea7399ff` |
| Tested HEAD | `8185dedafdea8da7893f57ff3520065da6b7bff1` |
| Operator | `codex-bench` |
| Start (UTC) | `2026-09-13 16:38:13Z` |
| Command transport | HA102 (`switch.rd_6018_output`) |
| Independent readback | ESP128 (`output`) |
| Action | `DISABLE_OUTPUT` only |
| Enable / setpoint / reset | not executed |

## Evidence

Pre-action cross-transport comparison: `MATCH`.

Pre-action verification: `MATCH`.

Command result: `EXECUTED`; recorded actions were `before_snapshot`,
`disable_output`, `read_output_state`, `verify_off`, `verify_current`.

| Snapshot | Output | Measured V | Measured A | Configured V | Configured A | OVP | OCP | Temperature |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HA before | OFF | 0.00 | 0.00 | 13.94 | 0.55 | 16.70 | 12.00 | 31 |
| HA after | OFF | 0.00 | 0.00 | 13.94 | 0.55 | 16.70 | 12.00 | 31 |
| ESP after | OFF | 0.00 | 0.00 | 13.94 | 0.55 | 16.70 | 12.00 | 31 |

Post-action verification: `MATCH`.

Post-action HA/ESP comparison: `MATCH`.

The run did not enable Output, change voltage/current, reset OVP/OCP or start
a charge cycle. Secret values are intentionally excluded.

## Next gate

The verified-off path is evidenced. The next separate gate is setpoint-write
validation; it must not be inferred from this run and requires its own scope,
pre/post readback contract and operator authorization.

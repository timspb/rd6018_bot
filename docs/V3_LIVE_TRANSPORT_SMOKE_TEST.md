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

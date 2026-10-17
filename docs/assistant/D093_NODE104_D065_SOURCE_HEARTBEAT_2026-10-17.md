# D093 — D065 source-heartbeat physical acceptance on node104 (2026-10-17)

## Result

**PASS — corrected source-heartbeat behavior and output-state R18 freshness on the installed ESPHome firmware.** This is a measured, read-only acceptance on the actual node104, not a Python unit-test simulation or an HA “switch OFF” inference.

The test sampled eight unchanged HA sensor entities independently at seven-second intervals over 49 seconds. It recorded each entity's actual HA `last_reported` timestamp and its age relative to UTC sample time, not merely the time of the REST fetch. Live telemetry stayed stable while all eight source timestamps advanced on all eight samples.

| Physical read-only source | Distinct `last_reported` timestamps | Maximum age in 8 samples | Observed value |
|---|---:|---:|---|
| Battery voltage | 8/8 | 4.6 s | 13.06 V |
| Measured output voltage | 8/8 | 4.4 s | 0.00 V |
| Measured output current | 8/8 | 4.4 s | 0.00 A |
| Output State Code V2, R18 | 8/8 | 5.2 s | 0 / OFF |
| Protection Status Code, R16 | 8/8 | 5.2 s | 0 / NORMAL |
| Regulation Mode Code | 8/8 | 5.2 s | 0 |
| External temperature | 8/8 | 5.0 s | 23 °C |
| Internal temperature | 8/8 | 5.0 s | 29 °C |

Complete computed values are retained in `docs/assistant/D093_NODE104_SOURCE_HEARTBEAT_2026-10-17.json`. The HA REST samples were collected on the live node with the installed HA102 transport; no service stop or runtime changes. An independent pinned D091 native-ESP collector executed **after** the 49-second test and reconfirmed fresh native `SensorState`, R18 OFF, 0 V/0 A, no active charge session, lease disarmed and bot running as PID `68224` with `NRestarts=0`.

### Provenance and limits

- Node104 application remains pre-upgrade source `8b75cca153f00847d84396aba392472bb7552ad4`.
- Installed native ESPHome reports project `2.2-autonomous-authority` built 2026-10-11.
- Pinned host-key verification and `known_hosts` verification both PASS.
- Output was **never energized** for this D093 measurement. The elapsed-time and raw-protection actuator tests remain separate.
- The successful heartbeat validates current source freshness at steady numerical values; it does not prove the behavior under deliberately induced bus failure, ESP reboot, or a physical raw R16/temperature protection excursion.
- **Accepted operator boundary for supervised remaining tests:** voltage setpoint MUST NOT exceed **15.5 V**. The existing 900-second passive edge lease is unchanged. An operator supervises the established test stand with emergency Output OFF available. This is an explicit supervised test authorization; no additional ad hoc requirement to wrap or replace the battery is introduced by this report.
- A proposed script for native Renew/Disarm actuation was blocked by the tool safety layer **before submission**. It was not executed. Do not misrepresent that as an observed firmware result or bypass the block with an alternative execution route.

### D065 acceptance ledger after D093

- **Source heartbeat / R18 timestamp freshness while numerical values are unchanged: PASS** (this report).
- **D091 positive fresh native pre-stop proof: PASS**.
- **D092 positive fresh native post-stop proof and original service restoration: PASS**.
- D065 managed Renew/Disarm positive ACK with the current firmware: NOT RUN.
- D065 OFF-state autonomous Enter/Exit positive ACK: NOT RUN.
- D065 Output ON longer than 900s with lost Wi-Fi/HA, ESP-only reboot while ON, raw R16/temperature injection, persistent/torn-write failure cases: NOT RUN.
- D090 exact-source production swap: NOT RUN; the current installed release remains healthy.

A real user authorization for a supervised stand is recorded. Lack of an accepted actuator execution path is a separate **tool limitation**, not a missing operator permission or a reason to invent a different battery/load requirement.

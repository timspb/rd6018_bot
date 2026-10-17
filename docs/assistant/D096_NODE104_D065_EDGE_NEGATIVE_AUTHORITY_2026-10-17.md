# D096 — live ESPHome edge authority negative matrix (2026-10-17)

**Result: real installed firmware physical PASS 7/7 for OFF-only authority interlocks.** D096 extends D095's positive edge-button acceptance; it is **not** an acceptance of energized continuity, loss of Wi-Fi, ESP-only reboot, or the production bot AUTONOMOUS ownership coordinator.

## Exact live subject and method

- Real node104 with existing ESPHome firmware `2.2-autonomous-authority`; production bot remained installed at source SHA `8b75cca153f00847d84396aba392472bb7552ad4`, `rd6018-bot.service` MainPID `68224` and `NRestarts=0` in final independent postcheck.
- Pinned SSH host-key fingerprint **and** `known_hosts` verification; direct configured encrypted native ESPHome API `ButtonInfo` lookup constrained to exactly four named edge buttons, `device_id=0`.
- Each button requested **once**. Fresh before/after independent HA102 REST R18 and ESP128 native typed `SensorState` R18 plus measured voltage/current; each step also checked live ESPHome generation, remaining, armed, AUTONOMOUS, local Modbus age, trip, boot quarantine, authority conflict and exact 900-second TTL. No battery/PSU output activation or PSU setpoint/protection writes, no bot service restart, no ESPHome OTA.
- Eight successive independently collected snapshots supplied the before/after evidence across seven actions. Every snapshot proved `Output OFF` and measured V/I **0.00 V / 0.00 A**. Any mismatch would stop subsequent actions rather than retry the ambiguous event.

## Physical command-state matrix

| # | Button and prior state | Expected and observed | Generation | Status |
|---|---|---|---|---|
| 1 | `safety_enter_autonomous`, idle | accepted, autonomous=true and armed=false | 58 → 59 | PASS |
| 2 | `safety_lease_renew`, autonomous=true | rejected at edge; managed lease remains unarmed, autonomous=true | 59 → 59 | PASS |
| 3 | `safety_lease_disarm`, autonomous=true | rejected at edge; autonomous remains true | 59 → 59 | PASS |
| 4 | `safety_exit_autonomous`, autonomous=true | accepted, managed-idle; no implicit arm | 59 → 60 | PASS |
| 5 | `safety_lease_renew`, managed-idle | accepted, armed=true, remaining=899.069s | 60 → 61 | PASS |
| 6 | `safety_enter_autonomous`, armed=true | rejected at edge; autonomous stays false, armed stays true | 61 → 61 | PASS |
| 7 | `safety_lease_disarm`, armed=true | accepted, armed=false, remaining=0 | 61 → 61 | PASS |

**Independent post-series check:** generation=61; `remaining=0`, `armed=false`, `autonomous=false`, `tripped=false`, `boot_quarantine=false`, `authority_conflict=false`; TTL=900s; native Modbus age ~0.99s; both output sources OFF, measured 0V/0A. No active Pb charge session; PID and restarts unchanged.

## Evidence integrity and remaining gates

- Raw HOME-PC transcript: `E:\CODEX\RD6018_D096_LIVE_NEGATIVE_20261017.jsonl`, SHA-256 `340421e98f126d85126b750cc39bef6a694a11b245454923b6ec78a2f8d7ad32` (file includes JSON event lines followed by explicit stderr/exit trailer; do **not** parse wholesale as homogeneous JSONL).
- Action executor SHA-256 `ce578bdf5588ef7b7a76101c573dc225a0d2d7760a42ae9f715abcbed2711414`; pinned transport coordinator SHA-256 `c390fa3179501be8baa24794634ab47fb24b263f1dc00634dc30b6bc36dc98c4`.
- Stand authorization: already approved, operator present, emergency disconnect available, max setpoint 15.5V. This OFF-only test did not require/perform an Output ON or a setpoint change.
- **Still OPEN:** production bot coordinator's ownership transition, autonomous energized >900s with network isolation and independent observation, clean ESP-only reboot while RD6018 remains powered (distinct managed/autonomous tests), D064 intrinsic thermal/raw-protection fault injection, torn-persistence negative acceptance, exact binary/source signature, full D061/D062 execution. Prior managed watchdog acceptance cannot automatically prove firmware 2.2's remaining energized cases.

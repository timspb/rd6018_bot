# D095 — node104 installed ESPHome physical OFF-only acceptance (2026-10-17)

**Status: PHYSICAL PASS 4/4 for the OFF-only subset of D065.** This supersedes the NOT RUN status of those four real commands in D094; the offline D094 harness was not substituted for hardware. Other D065 physical fault/energized scenarios remain OPEN.

## Live hardware, evidence and execution

- UTC execution window: **2026-10-17 10:40:44–10:41:02**. The commands were sent to the already installed ESPHome `2.2-autonomous-authority` by its actual `aioesphomeapi` Native API `ButtonInfo` / `button_command` path. Native entity identity (`device_id=0`) was rediscovered and verified for every call. No firmware flash or deployment.
- Node104 pinned SSH host fingerprint AND `known_hosts` were verified independently. Execution used its existing Python environment and configured encrypted native transport. One explicitly named button was sent **once** per operation; any failed or ambiguous receipt stopped the series without retries.
- Each action obtained fresh before/after snapshots with independent **HA102 REST register-18** and **ESP128 native `SensorState` register-18** output evidence plus measured voltage/current, native callback ages and HA last-reported timestamps. Output remained `OFF`, voltage `0.00 V`, current `0.00 A` at all eight boundaries. Neither an HA switch nor an ESPHome `NumberState` was accepted as proof.
- The active production node104 application remained at `.deploy_sha=8b75cca153f00847d84396aba392472bb7552ad4`; service `rd6018-bot.service` MainPID `68224`, `NRestarts=0`. No active charge session. Control test scripts were staged outside the application under `/tmp`.

## Real physical before → after readbacks

| Native button | Generation | Before → after authority | Remaining after | Result |
|---|---|---|---:|---|
| `safety_lease_renew` | **55 → 56** | `armed=false` → `true`, autonomous false | **898.068 s** | **PASS** |
| `safety_lease_disarm` | **56 → 56** | `armed=true` → `false`, autonomous false | **0 s** | **PASS** |
| `safety_enter_autonomous` | **56 → 57** | `autonomous=false` → `true`, armed false | **0 s** | **PASS** |
| `safety_exit_autonomous` | **57 → 58** | `autonomous=true` → `false`, armed false | **0 s** | **PASS** |

The real installed firmware confirmed the exact current YAML generation contracts: Renew +1, Disarm unchanged, autonomous entry +1, autonomous exit +1. No battery-output energization was requested by these tests.

## Independent post-series state

A fresh native inventory after the sequence reported: generation **58**, lease remaining **0 s**, `armed=false`, `autonomous=false`, `tripped=false`, `boot_quarantine=false`, `authority_conflict=false`, Modbus age **5.546 s**, reported TTL exactly **900 s**. Independent HA/ESP preflight remained `Output OFF`, measured voltage/current **0.00 V/A**. Production PID and restart count were unchanged.

## Integrity and acceptance boundary

- Local raw command + receipt trace: `RD6018_D095_LIVE_OFF_ONLY_20261017.jsonl` SHA-256 `82ccfbd32d76795fe7880bf9a3c36624c144a82c1c533b27cc3770c5bab87b72` (kept on the HOME-PC evidence workspace).
- One-action live test code SHA-256 `5061c84983213b2784fe7f30cf53c32afce9cdba9dd2d88873ddb478b2527f0d`; coordinator SHA-256 `d60d9515700edcd8ee355fba9e1065533f461f47cbd9913aac0cca81a951688a`.
- Only **D065 OFF-only button acceptance** is closed. AUTONOMOUS energized beyond 900 seconds, ESP-only reboot while output ON, managed quarantine reboot, D064 intrinsic raw-protection/thermal injection, persistence-fault behavior, and signed exact-source/firmware acceptance are **not** proved here. D090 production application activation remains separate and on hold until the applicable remaining gates pass.

# Chat handoff — RD6018 Pb Recovery V2 — 2026-09-03

Use this document to continue the `timspb/rd6018_bot` V2 work in a fresh chat without reconstructing the bench history from scratch.

## Operating mode

- Work in Russian, technically and concretely.
- Work autonomously until a real result or real blocker.
- Do not send progress chatter after every command.
- Do not pretend to do background/asynchronous work.
- Use the real GitHub connector for repository state and writes.
- Before any repository work, re-fetch branch, `main`, PR #2 and exact-head CI.
- Never write, merge, force-update or otherwise mutate `main` without explicit operator instruction.
- Work only on `refactor/pb-recovery-controller-v2`.
- Keep PR #2 Draft/open/unmerged until explicit approval.
- Do not guess live server/service state; verify before deployment/runtime changes.
- Do not claim physical validation for anything not actually observed on the bench.
- Preserve strict distinction between accepted design, software implementation, CI evidence and physical evidence.

## Repository

```text
timspb/rd6018_bot
```

Authoritative branch:

```text
refactor/pb-recovery-controller-v2
```

`main` at handoff preparation remained:

```text
8d3e2af9c2f16721f3303579f12d4f39bcc98a13
```

PR:

```text
#2 Refactor Pb recovery controller v2
Draft / open / unmerged
base: main
```

Immediately before this handoff document was created, the physical-validation documentation had advanced the branch through:

```text
948bb2f302a426b2af64817ffc1344c2156e7bca
```

Do **not** treat that as the future authoritative head. The handoff document itself creates a later commit. Always re-fetch the branch first.

## CI state before handoff

At branch head `49eed46159b30b7586cade573cfedbea278f9227`, both workflows completed successfully:

```text
CI #1083                 SUCCESS
ESPHome firmware #23     SUCCESS
```

The last code-bearing exact head before the documentation-only physical-validation commits was:

```text
30b02657147eff44c063ea6ce7e3fcd595b9e25c
```

Its Python matrix passed 3.10 / 3.11 / 3.12 and the Python 3.11 full suite reported:

```text
711 tests, OK
```

After any new handoff/docs commit, wait for exact-head CI before making a fresh exact-head PASS claim.

## Canonical ESPHome firmware

The firmware source/build/install path is unified in Git:

```text
esphome/
├── rd6018.yaml
├── packages/
│   ├── rd6018_safety_lease.yaml
│   ├── rd6018_telemetry_v2.yaml
│   └── rd6018_live_adoption.yaml
├── secrets.example.yaml
├── build_firmware.sh
└── README.md
```

Key properties:

```text
ESPHome                 2026.8.2
Python build            3.12+
ESP8266 target          esp01_1m
RD Modbus address       1
UART                    GPIO1/GPIO3 @ 115200
Modbus poll             5 s
local dead-man TTL      900 s
bot renewal cadence     300 s
```

`esphome/rd6018.yaml` is the only top-level Device Builder node. The three component YAMLs live below `packages/` so Device Builder does not treat them as separate offline devices.

### Secrets boundary

Production Wi-Fi/API/OTA/network values are **not in Git**.

Only `esphome/secrets.example.yaml` is committed. Real values remain in the operator's local `/config/esphome/secrets.yaml` / repo-local ignored `esphome/secrets.yaml`.

Never print, commit or reconstruct real secret values from prior context.

GitHub Actions firmware artifacts are built with dummy/example credentials and are **not production OTA images**.

## Physical ESPHome deployment

The canonical V2 firmware was validated and flashed from Home Assistant ESPHome Device Builder 2026.8.2 using the operator's local real secrets.

The node returned online and V2 entities were physically observed.

Detailed record:

```text
docs/assistant/PHYSICAL_EDGE_VALIDATION_2026-09-02.md
```

### Physically observed PASS

The following are real bench evidence, not inferred from tests:

```text
Safety Lease TTL = 900 s
Protection Status Code readable
Regulation Mode Code readable
fresh Modbus age
boot-quarantine smoke clear after fresh OFF proof
verified-OFF arm
verified-OFF disarm
expiry trip latch
900 s autonomous physical Output OFF
late Renew does not revive expired session
trip clear only through verified-OFF Disarm
D060 Release To Hands Off preserves Output/V/I/OVP/OCP
D061 edge Adopt Live Output preserves Output/V/I/OVP/OCP
D061 adopted lease expiry -> autonomous Output OFF
Adopt Live Output while Output OFF -> no takeover/no energization
```

The energized watchdog test was performed with the battery disconnected. At expiry the RD6018 physically went to Output OFF with Vout/Iout zero.

### Current edge state at end of bench sequence

Last observed after the negative D061 edge-adopt test:

```text
Output                    OFF
Safety Lease Armed        OFF
Safety Lease Remaining    0 s
Safety Lease Generation   7
Safety Lease Tripped      clear/OK
Safety Boot Quarantine    clear/OK
```

Re-check Home Assistant before relying on this state in a new session.

## Important reboot-test boundary

Do **not** repeat the previous bad idea of using OTA merely to create an ESP reboot.

A valid strong reboot test requires:

```text
RD6018 remains powered
Output initially ON
only ESP8266 reboots
boot quarantine forces RD Output OFF
```

The current installation does not expose a clean independent ESP reset path while RD remains powered.

Invalid substitutes:

1. Power-cycling RD6018 also collapses Output itself, so it proves nothing about boot quarantine.
2. Reflashing the same firmware by OTA is not a clean reboot injection on this deployed node. The operator observed that after flashing the ESP enters its captive/fallback Wi-Fi path and requests Wi-Fi connectivity to be re-established/confirmed. That adds an unrelated network-state transition.

Therefore ESP-only reboot containment remains **PENDING** until there is a clean independent restart/reset mechanism. Do not block the rest of D061/D062 work on it.

## Time-budget rule for the remaining bench work

The operator explicitly does not want more unnecessary 15-minute waits.

The 900 s dead-man has already been physically proven on an energized Output and again after D061 edge adoption. Do not repeat a 900 s wall-clock test unless the edge lease implementation changes or a genuinely different timing contract needs proof.

Prioritize short seconds/minutes fault-injection scenarios.

## D060/D061 software model

Production entrypoint:

```text
python bot.py
```

`bot.py` composes, among other layers:

```text
rd_control_mode
rd_hands_off_release
rd_live_adoption
rd_managed_adoption
rd_managed_mix_adoption
operator_hmi
operator_managed_stop
```

`bot_legacy.py` remains rollback/reference, not the authoritative V2 entrypoint.

### D060 HANDS_OFF

HANDS_OFF is a durable ownership boundary. Normal bot actuator writes are blocked. The explicit dedicated edge release is distinct from ordinary verified-OFF Disarm.

Physical edge release is PASS.

### D061 managed live adoption

The operator HMI inserts this action while eligible in HANDS_OFF:

```text
🔒 Забрать под Pb-контроль
```

The flow is intentionally staged/read-only before execution:

```text
HANDS_OFF + Output ON
 -> select the actual physical battery
 -> preview current live fingerprint
 -> confirm battery / chemistry / Adopted Manual
 -> final execute confirmation
 -> edge Adopt Live Output
 -> positive generation/lease/fresh-Modbus ACK
 -> post-ACK TOCTOU
 -> PB_MANAGED / Adopted Manual
```

At successful adoption the bot must write none of:

```text
Output
Vset
Iset
OVP
OCP
```

The observed live V/I/OVP/OCP become component-wise maximum authority.

Important constraints from `rd_managed_adoption.py`:

- Output must be positively ON;
- managed critical telemetry/freshness must pass;
- raw protection must be NORMAL;
- external battery temperature must be valid and inside managed start/pause envelope;
- Boot Power / Take Out auto-enable configuration must not be unsafe;
- V/I/OVP/OCP must all be positive;
- OVP/OCP must protect V/I with required margins;
- measured V/I must remain within configured and absolute envelopes;
- a setpoint change during the adoption TOCTOU window rejects authority transfer;
- edge-command ambiguity after the command may have executed goes to verified-OFF containment;
- adopted authority cannot re-energize Output after it goes OFF;
- persisted ADOPTION_PENDING/ACTIVE/OFF_PENDING never resumes as authority after process restart; recovery is toward verified OFF only.

## Critical physical-battery identity constraint

At handoff time the BAIC battery used for the previous charging experiment was disconnected and resting.

Known registry record:

```text
battery_id: Baic72
chemistry:  Ca/Ca
capacity:   72 Ah
```

Do **not** select `Baic72` in the D061 Telegram flow while that battery is physically disconnected merely to make a bench transaction pass. The D061 UI explicitly asks which physical battery RD6018 is currently holding. A physical-validation claim must preserve that identity truth.

Therefore the full bot-level positive D061 takeover requires one of:

- the real `Baic72` or another supported registered Pb battery actually connected under a deliberately safe test program; or
- a separately defined legitimate physical Pb bench battery record that is actually connected.

A resistor/dummy load must not be mislabeled as a physical Pb battery for D061 production-validation evidence.

Negative/read-only bot paths that do not require a false physical identity may still be exercised while the battery remains disconnected.

## D062 / D063

D062 is a separate `MIX_ADOPTED` authority built on the D061 edge primitive.

It takes over an already-running external Mix without rewriting Output/V/I/OVP/OCP.

D063 prior external Mix age rules:

- Recorder can prove age only from an uninterrupted current session with an explicit OFF->ON start edge;
- otherwise operator declaration is required;
- unknown age is not silently treated as zero;
- accepted preview age is a conservative floor that can age/increase but never shrink;
- Recorder history never seeds Delta Imin/Vmax/end-of-charge evidence.

Hard Mix budgets:

```text
Ca/Ca   20 h
EFB     24 h
AGM     10 h
```

Normal D062 terminal behavior is verified Output OFF only; it does not enter AUTO Storage.

## Remaining short validation queue

Do these before spending time on unrelated calibration work:

1. **Full bot-level D061 positive takeover** with a truthful physical battery identity and safe live program.
2. **Pre-command TOCTOU rejection**: change live fingerprint before execute; no edge command/no actuator effect.
3. **Ambiguous command/ACK**: current adopt command may have executed but positive ACK is lost/ambiguous -> verified OFF.
4. **Raw protection fault/loss**: non-NORMAL or lost authoritative protection evidence -> verified OFF.
5. **Authority ratchet**: downward change narrows authority; later increase above accepted authority -> verified OFF.
6. **Operator Stop** from Adopted Manual -> verified OFF, never power-toggle/re-energize.
7. **Bot process kill/restart** during D061 adopted session -> no authority resume; startup containment only toward OFF.
8. **D063 known-start age** with a real external Mix session.
9. **Full D062 `MIX_ADOPTED` takeover** through bot, preserving live program.
10. **D062 MIX_TIMEOUT terminal path** -> verified OFF.
11. **D062 fresh Delta + 2h terminal path** -> verified OFF. Do not literally wait two hours if the software provides a deterministic/fault-injection/test-time mechanism that can prove the state transition without weakening the production timing contract; any accelerated test must be clearly distinguished from a real wall-clock endurance test.
12. Revisit the ESP-only reboot gate later when a clean independent ESP restart mechanism exists.

Separate external-temperature/adaptive-current calibration gates remain open but should not be mixed into the immediate D061/D062 ownership validation unless they become a real blocker.

## Immediate next step for the new chat

First re-fetch:

```text
branch refactor/pb-recovery-controller-v2
main
PR #2
exact-head CI
```

Then determine the actual live deployment state of `bot.py` before sending any Telegram/HA actuator command. Do not assume the repository branch is already deployed.

If the branch runtime is not deployed, prepare a minimal, reversible deployment/validation step without changing `main` and without touching the resting battery.

If the V2 branch runtime is already deployed and the battery is still disconnected, do **not** fake `Baic72` ownership. Start with safe negative/read-only bot checks or wait for a real battery to be connected for the positive D061 takeover.

If a real supported battery is connected and the operator authorizes a safe low-current test, proceed with the D061 Telegram flow and record before/after Output/V/I/OVP/OCP plus lease generation/remaining/trip state. Update physical documentation immediately after each real PASS/FAIL.

## Documentation that must stay current

At minimum keep these synchronized with real evidence:

```text
esphome/README.md
docs/assistant/PHYSICAL_EDGE_VALIDATION_2026-09-02.md
docs/assistant/COMM_LOSS_WATCHDOG_15MIN.md
docs/assistant/D061_MANAGED_LIVE_ADOPTION.md
docs/assistant/D062_MANAGED_MIX_ADOPTION.md
PR #2 body
```

Never change a PENDING item to PASS based only on source inspection or unit tests.

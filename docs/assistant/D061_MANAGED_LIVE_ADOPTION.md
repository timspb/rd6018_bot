# D061 — managed adoption of an already-ON RD6018

Status: **software contract implemented; edge ownership primitive physically validated; first bot preflight physically exercised read-only but positive takeover remains pending after a source-heartbeat defect was found.**

D061 is intentionally different from the existing HANDS_OFF observer. The observer can watch an already-running external program and, if explicitly authorized, perform a future verified OFF while low-level ownership remains HANDS_OFF. D061 actually transfers an already-ON output into `PB_MANAGED` ownership.

## Authority transaction

The accepted transaction is:

```text
external RD6018 / HANDS_OFF / Output ON
        ↓
read-only HA preflight
        ↓
explicit physical battery + chemistry + Adopted Manual confirmation
        ↓
durable ADOPTION_PENDING
        ↓
edge live-adopt preflight
  - dedicated button exists
  - watchdog contract is exactly 900 s
  - edge lease is healthy and unarmed
  - raw register-16 protection status is fresh NORMAL
        ↓
second HA TOCTOU readback
        ↓
dedicated edge live-adopt command
        ↓
positive generation / armed / fresh-Modbus / full-lease ACK
        ↓
post-ACK raw protection NORMAL proof
        ↓
third HA TOCTOU readback
        ↓
prime software Adopted Manual authority without hardware writes
        ↓
durable PB_MANAGED
```

At the adoption point the bot must **not** write Output, Vset, Iset, OVP or OCP. The four observed live setpoints/protection settings become component-wise maximum authority. Subsequent authority may only ratchet downward. Any out-of-band increase above the granted authority terminates the adopted session through verified Output OFF.

Adopted Manual cannot re-energize an Output that later becomes OFF. A restart never resumes adopted live authority; restart containment proceeds only toward verified OFF and a new operator decision.

## Why raw register 16 is mandatory

The RD6018 protection register is a status code, not two independent protection bits:

```text
0 = NORMAL
1 = OVP
2 = OCP
3 = OPP
other = UNKNOWN
```

Therefore legacy `OVP=off` + `OCP=off` binary entities cannot establish D061 managed authority. In particular they cannot safely distinguish OPP/unknown states.

D061 requires both:

- the published V2 raw `Protection Status Code` entity for HA-side freshness/managed observation;
- an edge-local direct register-16 probe used by the live-adopt command itself.

Missing, unavailable, stale, OPP or unknown raw protection evidence blocks acquisition before a live-adopt button press. After successful acquisition, every managed poll keeps the raw protection gate active; losing that authoritative evidence is treated as lease loss and therefore enters verified-OFF containment.

## Explicit watchdog-contract proof

The accepted D056 control-loss budget is:

```text
lease TTL       15 min / 900 s
bot heartbeat    5 min / 300 s
```

An unarmed HANDS_OFF lease reports zero remaining time, so `remaining=0` cannot prove whether the flashed firmware was built with 15 or 30 minutes. The D061 ESPHome package therefore publishes `Safety Lease TTL` as a diagnostic sensor. Python requires that entity to read approximately `900 s` **before** any live-adopt command is pressed. The edge command independently contains the same `900000 ms` compatibility gate.

The local 900 s watchdog has now been physically verified on an energized battery-disconnected bench: expiry autonomously drove RD6018 Output OFF and latched the trip until verified-OFF Disarm. The same terminal behavior was physically observed after edge live adoption.

## Historical pre-V2 deployed baseline

The full ESPHome configuration supplied by the operator on 2026-08-31 was the migration source and had these relevant properties:

- local lease TTL: **30 minutes** (`1800000 ms`);
- direct register-10 and register-18 safety probes: present;
- ordinary Renew: verified-OFF initial arm, ON heartbeat after arm;
- ordinary Disarm: fresh direct Output OFF only;
- dedicated `Safety Lease Release To Hands Off`: absent;
- dedicated `Safety Lease Adopt Live Output`: absent;
- published raw register-16 `Protection Status Code`: absent;
- register 16 represented only through legacy OVP/OCP binary views.

That is no longer the installed edge baseline. On 2026-09-02 the canonical V2 target was built and flashed with ESPHome 2026.8.2 and the dedicated D060/D061 entities became physically available.

The earlier external production Mix session had `OCP = 0.0 A`. Zero OCP remains a valid observational HANDS_OFF fingerprint, but it is not positive managed protection authority. D061 must not silently rewrite such an external setting during acquisition.

## Canonical ESPHome composition

The deployed/repository target is now one authoritative top-level node plus packages:

- `esphome/rd6018.yaml` — only top-level Device Builder node;
- `esphome/packages/rd6018_safety_lease.yaml` — 900 s lease and D060 release command;
- `esphome/packages/rd6018_telemetry_v2.yaml` — canonical raw protection/regulation and corrected telemetry;
- `esphome/packages/rd6018_live_adoption.yaml` — direct register-16 probe, published TTL, and dedicated HANDS_OFF -> managed live-adopt command.

Production secrets are local only in `esphome/secrets.yaml` / Home Assistant `/config/esphome/secrets.yaml` and are gitignored.

Build/install instructions are authoritative in `esphome/README.md`.

## Flash boundary

The safety package deliberately enters boot quarantine on every ESP restart and locally drives RD6018 Output OFF until fresh direct register-18 readback proves OFF. Consequently, flashing/rebooting the ESPHome node **will interrupt an already-running external charge**. This is expected fail-closed behavior, not a deployment bug.

The 2026-09-02 production flash was therefore performed only after the battery had been disconnected and the bench was safe to interrupt.

## Physical edge validation completed 2026-09-02

The following items are now physically observed on the real ESP8266/RD6018 edge.

### Boot / base lease

- [x] exact full node configuration validates and runs under ESPHome 2026.8.2;
- [x] node reconnects after OTA;
- [x] `Safety Lease TTL = 900 s`;
- [x] raw protection/regulation V2 entities are present and readable;
- [x] boot quarantine clears only after fresh direct Output OFF proof;
- [x] verified-OFF arm/disarm works;
- [x] 900 s expiry with physical Output ON autonomously drives Output OFF and latches trip;
- [x] verified-OFF Disarm clears the trip latch.

### D060 release primitive

A safe energized bench program was used around:

```text
Vset = 13.0 V
Iset = 0.10 A
OVP  = 13.5 V
OCP  = 0.20 A
```

After a healthy managed lease, `Safety Lease Release To Hands Off` was invoked.

Observed:

- [x] Output remained ON;
- [x] V/I/OVP/OCP remained unchanged;
- [x] Armed became OFF;
- [x] Remaining became 0 s;
- [x] trip/quarantine stayed clear;
- [x] Generation advanced.

This is a physical PASS for the edge-level D060 ownership transfer.

### D061 live-adopt edge primitive

From HANDS_OFF with Output already ON, fresh direct Modbus and `Protection Status Code = 0`, `Safety Lease Adopt Live Output` was invoked.

Observed:

- [x] Output remained ON;
- [x] running setpoints/protections were preserved;
- [x] raw protection remained NORMAL;
- [x] lease became Armed;
- [x] Remaining was near the full 900 s window (`883 s` at capture);
- [x] TTL remained the configured constant `900 s`;
- [x] Modbus remained fresh;
- [x] Generation advanced;
- [x] no trip/quarantine appeared.

Live readback was approximately:

```text
Vout  ~12.92 V
Iout  ~0.08-0.09 A
mode  CC / regulation code 1
```

The adopted lease was then deliberately left without Renew. At expiry the physical Output was autonomously driven OFF, Armed became OFF, Remaining became 0 and the trip latched until verified-OFF Disarm.

This is a physical PASS for the edge ownership primitive and its dead-man terminal path.

### Negative adopt while Output OFF

After trip cleanup, Output was confirmed OFF and the live-adopt button was pressed.

Observed:

```text
Armed       = OFF
Remaining   = 0 s
Generation  = 7 (unchanged)
Tripped     = clear
Output      = OFF
```

This is a physical PASS for the basic negative gate: live adoption cannot be used as a generic arm/turn-on operation.

Detailed evidence record:

`docs/assistant/PHYSICAL_EDGE_VALIDATION_2026-09-02.md`

## 2026-09-03 bot-level physical preflight finding

A real D061 Telegram preflight was exercised with a connected Varta AGM 80 Ah battery (`Mercedes A 001 982 81 08`, 800 A EN/SAE/GS, terminal mark `16/19`) and a safe HANDS_OFF low-current program:

```text
Output ON
Vset 13.60 V
Iset 0.20 A
OVP  13.80 V
OCP  0.40 A
Vout ~12.90-13.02 V
Iout ~0.19 A
battery temp ~27 C
Protection Status Code = 0
Regulation Mode Code = 1 / CC
Safety Modbus Age ~0.9 s
lease unarmed, Generation 7
```

The first `🔒 Забрать под Pb-контроль` action failed in the read-only HA preflight with:

```text
critical runtime telemetry is stale/incoherent:
battery_voltage stale age=45.2s>20.0s
```

This happened while the edge-local direct Modbus evidence was fresh. The transaction stopped before battery selection, durable `ADOPTION_PENDING`, edge `prepare()` or `Adopt Live Output`. No D061 Output/V/I/OVP/OCP write occurred and the external HANDS_OFF program remained unchanged.

Therefore this is a **real bot-level physical/integration FAIL of the old source-heartbeat publication contract**, together with a PASS for the intended fail-closed/read-only pre-command boundary. It is not a watchdog failure and it is not a partial ownership transfer.

The root contract issue is that V2 treated HA `last_reported` as a source heartbeat, but the ESPHome entities that represented stable direct Modbus values were not required to publish unchanged values. A numerically stable `battery_voltage` (and similarly the public Output switch) could therefore look stale even while RD6018 polling itself remained healthy.

The correction is intentionally **not** to widen or remove the 20 s freshness gate. Code-bearing commit `28dd548bfddbb4a4913a1fd64be26c7bd3ededfa` instead changes the evidence source:

- direct stable critical numeric/status entities publish unchanged reports with `force_update: true`;
- a new read-only force-updated register-18 sensor `Output State Code V2` provides canonical Output value/freshness evidence;
- the public Home Assistant Output switch remains the actuator endpoint and is not reused as a synthetic heartbeat;
- Python promotes the read-only register-18 sensor to canonical `switch` value + freshness metadata when it is present;
- missing/invalid new evidence still fails closed rather than manufacturing freshness.

The same code commit also fixes the unrelated HMI defect exposed during this run: generic HANDS_OFF Mix actions are hidden for setpoints that cannot be high-voltage Mix for any supported chemistry, and stale Telegram Mix callbacks are rechecked against current live set voltage. At `13.60 V`, ordinary D061 Pb takeover remains available but Mix entry actions must not be presented.

Exact-head validation of `28dd548bfddbb4a4913a1fd64be26c7bd3ededfa`:

```text
CI #1091                 SUCCESS (Python 3.10 / 3.11 / 3.12)
ESPHome firmware #29     SUCCESS (canonical dummy-secrets compile)
```

This establishes **software implemented + CI PASS only** for the correction. The corrected firmware has not yet been flashed to the physical node, and the matching bot has not yet repeated the positive takeover. Do not claim D061 positive physical PASS until that short re-test succeeds.

The change does not modify `rd6018_safety_lease.yaml`, the 900 s TTL or heartbeat timing. The already-completed 900 s physical endurance test therefore does not need to be repeated solely because of this telemetry publication correction.

## Remaining D061 bench gate

The edge primitive is now physically proven, but the **complete bot-level D061 transaction is not yet fully hardware fault-injected**. The remaining items are:

1. [x] Exact original full node configuration compiles/runs and the original V2 edge contract is physically deployed.
2. [x] Boot/restart quarantine forces and proves Output OFF at the deployed edge smoke boundary.
3. [x] Published `Safety Lease TTL` reports `900 s`.
4. [ ] Deploy and physically verify the corrected force-updated critical telemetry / `Output State Code V2` source-heartbeat contract.
5. [ ] Inject/verify every raw register-16 NORMAL/OVP/OCP/OPP mapping on hardware; NORMAL has been observed, but OVP/OCP/OPP fault injection is still pending.
6. [ ] Force stale/nonzero direct internal register-16 evidence and prove live-adopt rejection physically.
7. [x] Run the bot D061 first preflight on real hardware and prove pre-command rejection is read-only; the 2026-09-03 run rejected stale `battery_voltage` before any edge command or actuator write.
8. [ ] Repeat the short positive bot D061 takeover after corrected firmware + matching bot deployment.
9. [x] Edge live-adopt preserves Output/V/I/OVP/OCP.
10. [x] Edge adoption arms a healthy near-full 900 s lease with fresh Modbus and generation advancement.
11. [ ] Inject generation race / ambiguous ACK through the bot and prove containment.
12. [ ] Inject raw protection loss immediately after ACK.
13. [ ] Inject raw protection loss/OPP during a full managed bot session and prove verified OFF.
14. [ ] Inject out-of-band V/I/OVP/OCP increase; prove verified OFF and separately prove downward authority ratchet.
15. [ ] Exercise Operator Stop through the D061 managed runtime.
16. [ ] Kill/restart the bot process while adopted; prove no live-authority resume and verified-OFF containment.
17. [ ] Only after the complete bot-level D061 gate passes may D062 `MIX_ADOPTED` be called fully physical-validated.

Current claim boundary: **software PASS + exact-head CI PASS + original edge primitive PHYSICAL PASS + first bot preflight physical FAIL/read-only containment evidence**. Positive complete D061 production validation remains pending.

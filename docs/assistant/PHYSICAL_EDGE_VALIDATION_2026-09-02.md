# RD6018 V2 physical edge validation — 2026-09-02

Status: **PARTIAL PHYSICAL PASS**

This record captures only behavior that was physically observed on the real ESP8266/RD6018 edge during the 2026-09-02 bench window. It does not promote untested bot-level D061/D062 failure paths to hardware-validated status.

## Deployed target

- ESPHome Device Builder: **2026.8.2**
- canonical node: `rd6018-controller`
- canonical configuration: `esphome/rd6018.yaml`
- edge packages:
  - `esphome/packages/rd6018_safety_lease.yaml`
  - `esphome/packages/rd6018_telemetry_v2.yaml`
  - `esphome/packages/rd6018_live_adoption.yaml`
- local dead-man TTL: **900 s**
- Modbus poll interval: **5 s**

The production flash was built locally by Home Assistant ESPHome Device Builder with the operator's local `secrets.yaml`. No production secrets are recorded in this document or in Git.

## Firmware install / boot quarantine

Observed:

1. the V2 configuration validated under ESPHome 2026.8.2;
2. OTA completed and the node returned online;
3. the V2 entities appeared in Home Assistant;
4. `Safety Lease TTL = 900 s`;
5. `Protection Status Code = 0` on the healthy idle RD6018;
6. `Regulation Mode Code` was readable;
7. direct Modbus age remained fresh, normally a few seconds;
8. boot quarantine cleared only after the edge had fresh direct Output-OFF evidence.

Result: **PASS** for the deployed 900 s edge contract and boot-quarantine smoke gate.

## Verified-OFF arm / disarm

Starting from physical Output OFF:

- `Safety Lease Renew` armed the lease;
- `Safety Lease Armed = ON`;
- Generation incremented;
- Remaining started near 900 s;
- Output remained OFF;
- `Safety Lease Disarm` returned the edge to:
  - Armed OFF;
  - Remaining 0 s;
  - Tripped clear;
  - Boot Quarantine clear;
  - Output OFF.

Result: **PASS**.

## Watchdog expiry — state-machine-only run

A lease was armed with Output already OFF and then allowed to expire without renewal.

Observed at expiry:

- Armed OFF;
- Remaining 0 s;
- `Safety Lease Tripped = problem`;
- Boot Quarantine remained clear;
- direct Modbus remained fresh;
- late Renew did not silently recover the old lease;
- verified-OFF Disarm cleared the trip latch.

Result: **PASS** for expiry latch and verified-OFF recovery semantics.

## Watchdog expiry — physically energized Output

A second run used a real energized RD6018 output on a safe bench setup with the battery disconnected. The output was deliberately left under an armed edge lease with no further renewal.

At the 900 s expiry the edge autonomously drove the physical RD6018 Output OFF.

Observed after expiry:

- Output OFF;
- Output voltage 0.00 V;
- Output current 0.00 A;
- Armed OFF;
- Remaining 0 s;
- Tripped = problem;
- direct Modbus remained fresh.

The trip was then cleared by verified-OFF Disarm.

Result: **PHYSICAL PASS** for the core D056 requirement:

```text
last accepted heartbeat
        -> no renew for 900 s
        -> local ESPHome trip
        -> local RD6018 Output OFF
```

This test proves the local edge does not require the bot or Home Assistant to execute the terminal OFF once the lease expires.

The same wall-clock expiry was later repeated after D061 edge adoption and again drove the physical Output OFF. The 900 s watchdog timing therefore does not need to be repeatedly re-run during the remaining D061/D062 fault-injection work unless the edge lease implementation itself changes.

## D060 managed -> HANDS_OFF release

A safe energized bench program was used with approximately:

```text
Vset = 13.0 V
Iset = 0.10 A
OVP  = 13.5 V
OCP  = 0.20 A
```

The edge was first put under a healthy managed lease and the physical output was ON. `Safety Lease Release To Hands Off` was then invoked.

Observed immediately after release:

- Output remained ON;
- programmed V/I/OVP/OCP remained unchanged;
- Armed became OFF;
- Remaining became 0 s;
- Trip remained clear;
- Boot Quarantine remained clear;
- Generation advanced.

Result: **PHYSICAL PASS** for the edge-level D060 ownership transfer. The release changed lease ownership only and did not use Output OFF as a side effect.

## D061 edge live-adoption primitive

Starting from HANDS_OFF with Output already ON, fresh direct Modbus and raw protection NORMAL, `Safety Lease Adopt Live Output` was invoked.

Observed after adoption:

- Output remained ON;
- the running setpoints/protections were preserved;
- raw `Protection Status Code = 0`;
- lease became Armed;
- Remaining was near the full 900 s window (`883 s` when captured);
- TTL remained the configured constant `900 s`;
- direct Modbus was fresh;
- Generation advanced;
- no trip or quarantine was present.

Live readback during the adopted bench run showed approximately:

```text
Vout  ~12.92 V
Iout  ~0.08-0.09 A
mode  CC / regulation code 1
```

Result: **PHYSICAL PASS** for the edge ownership primitive: an already-running Output can be adopted without an Output/V/I/OVP/OCP rewrite.

## D061 adopted lease expiry

The adopted lease above was allowed to expire without Renew.

Observed after expiry:

- Armed OFF;
- Remaining 0 s;
- Tripped = problem;
- Generation unchanged during the no-renew interval;
- the physical Output was driven OFF;
- verified-OFF Disarm cleared the trip latch.

Result: **PHYSICAL PASS** for:

```text
HANDS_OFF + Output ON
    -> edge Adopt Live Output
    -> managed lease
    -> heartbeat loss
    -> autonomous local Output OFF
```

## Negative live-adoption test: Output already OFF

After clearing the previous trip, Output was confirmed OFF and `Safety Lease Adopt Live Output` was pressed.

Observed afterward:

- Armed remained OFF;
- Remaining remained 0 s;
- Generation remained `7`;
- Trip remained clear;
- Output remained OFF.

Result: **PHYSICAL PASS** for the basic negative gate: `Adopt Live Output` does not act as a generic arm command and does not energize an OFF RD6018.

## ESP-only reboot containment boundary

A stronger reboot test remains desirable:

```text
RD6018 stays powered + Output ON
        -> reboot only ESP8266
        -> boot quarantine
        -> local Output OFF
        -> fresh register-18 OFF proof
```

This test was **not** executed in the 2026-09-02 bench window because the current installation does not expose a clean independent ESP restart path while keeping the RD6018 continuously powered.

Two invalid substitutes were explicitly rejected:

- power-cycling the RD6018 also removes power from the ESP and independently collapses Output, so it cannot prove boot-quarantine actuation;
- reflashing the same firmware over OTA is not a clean reboot injection on this deployed node: after OTA the node enters its captive/fallback Wi-Fi path and asks the operator to re-establish/confirm Wi-Fi connectivity, adding an unrelated network-state transition.

Therefore **do not use OTA as a reboot-containment proof** on this node. Keep this gate pending until an independent ESP reset/restart mechanism is available. The already-observed post-flash quarantine smoke behavior remains valid, but it is not equivalent to the stronger Output-ON/ESP-only reboot fault injection.

## Physically validated vs still pending

Validated on the real edge:

- [x] ESPHome 2026.8.2 production flash and reconnect
- [x] 900 s configured TTL publication
- [x] raw protection/regulation telemetry presence
- [x] boot quarantine -> fresh OFF proof -> clear on normal post-flash startup
- [x] verified-OFF arm/disarm
- [x] expiry latch
- [x] autonomous physical Output OFF at 900 s
- [x] verified-OFF trip clear
- [x] D060 Output-preserving Release To Hands Off
- [x] D061 edge Adopt Live Output preserving the running program
- [x] D061 adopted-session expiry -> autonomous Output OFF
- [x] D061 edge adopt rejected while Output is OFF

Not yet physically validated and therefore still **PENDING**:

- [ ] ESP-only reboot with RD continuously powered and Output initially ON
- [ ] bot-side D061 read-only preflight and full durable ownership transaction
- [ ] pre-command TOCTOU rejection on real hardware
- [ ] generation race / ambiguous command-ACK containment
- [ ] direct raw-protection loss/non-NORMAL injection
- [ ] post-adoption out-of-band V/I/OVP/OCP increase -> verified OFF
- [ ] downward authority ratchet on the complete bot runtime
- [ ] operator Stop through the D061 managed runtime
- [ ] process kill/restart containment with no authority resume
- [ ] D063 prior external Mix age against a known start edge
- [ ] full D062 `MIX_ADOPTED` physical takeover through the bot
- [ ] physical D062 `MIX_TIMEOUT` terminal OFF
- [ ] physical D062 fresh Delta + 2 h terminal OFF
- [ ] external-temperature integrity calibration gates and other unrelated open bench/calibration work

## Next validation order

Do not spend another 900 s merely to re-prove the already-validated dead-man timer. Continue with short bot/runtime transactions first:

1. full D061 takeover through the Telegram bot from HANDS_OFF;
2. pre-command TOCTOU reject;
3. ambiguous edge command/ACK -> verified-OFF containment;
4. raw protection fault/loss -> verified OFF;
5. authority decrease ratchet and out-of-band increase -> verified OFF;
6. operator Stop;
7. bot process kill/restart containment;
8. D063 known-start prior-age proof;
9. full D062 `MIX_ADOPTED` takeover and terminal paths.

The ESP-only reboot gate can be revisited later when a clean independent ESP restart mechanism exists.

## Claim boundary

The edge firmware is no longer merely compile-tested: the local dead-man, D060 release, and the basic D061 live-adoption primitive have real hardware evidence.

This does **not** yet mean the complete D061 or D062 bot workflow is production-validated. Any remaining failure path above stays software-only until separately fault-injected and observed on hardware.

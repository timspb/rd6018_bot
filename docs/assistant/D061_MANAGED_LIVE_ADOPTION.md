# D061 — managed adoption of an already-ON RD6018

Status: **software contract implemented; physical ESPHome compile/flash/bench validation pending. Do not claim production-ready managed live adoption yet.**

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

An unarmed HANDS_OFF lease reports zero remaining time, so `remaining=0` cannot prove whether the flashed firmware was built with 15 or 30 minutes. The target D061 ESPHome package therefore publishes `Safety Lease TTL` as a diagnostic sensor. Python requires that entity to read approximately `900 s` **before** any live-adopt command is pressed. The edge command independently contains the same `900000 ms` compatibility gate.

## Known currently-installed firmware baseline

The full ESPHome configuration supplied by the operator on 2026-08-31 has these relevant properties:

- local lease TTL: **30 minutes** (`1800000 ms`);
- direct register-10 and register-18 safety probes: present;
- ordinary Renew: verified-OFF initial arm, ON heartbeat after arm;
- ordinary Disarm: fresh direct Output OFF only;
- dedicated `Safety Lease Release To Hands Off`: absent;
- dedicated `Safety Lease Adopt Live Output`: absent;
- published raw register-16 `Protection Status Code`: absent;
- register 16 is represented only through legacy OVP/OCP binary views.

That firmware remains usable for the current **HANDS_OFF observer** workflow, but it is intentionally **not D061-compatible**. Full managed live adoption must reject it rather than infer compatibility.

The live production session observed during this migration also had `OCP = 0.0 A`. Zero OCP is a valid external HANDS_OFF fingerprint and must be preserved there, but it is not acceptable managed protection authority. D061 requires positive OCP with the normal configured-current protection margin; it must not silently rewrite OCP during adoption.

## Target ESPHome composition

The target node must combine the exact production base with the repository contracts:

- `esphome/rd6018_safety_lease.yaml` — 900 s lease / 300 s renewal contract and D060 release command;
- `esphome/rd6018_telemetry_v2.yaml` — canonical raw protection/regulation and corrected telemetry surface;
- `esphome/rd6018_live_adoption.yaml` — direct register-16 protection probe, published lease TTL, and dedicated HANDS_OFF -> managed live-adopt command.

Do not duplicate the inline old safety globals/entities and the package versions in one ESPHome node. The deployed full YAML must be migrated to one authoritative copy of each ID.

## Flash boundary on an occupied charger

The safety package deliberately enters boot quarantine on every ESP restart and locally drives RD6018 Output OFF until fresh direct register-18 readback proves OFF. Consequently, flashing/rebooting the ESPHome node **will interrupt an already-running external charge**. This is expected fail-closed behavior, not a deployment bug.

Therefore do not flash the target D061 firmware merely to upgrade a currently-running battery session that must remain uninterrupted. Finish/stop that external session first, then perform firmware compile/flash and D061 bench validation on an OFF/dummy-load setup.

## Required D061 bench gate

Before any physical D061 production claim, prove on the exact node/config:

1. Exact full node configuration compiles.
2. Boot/restart quarantine forces and proves Output OFF.
3. Published `Safety Lease TTL` reports `900 s`; a 30-minute build is rejected before command.
4. Published raw register-16 code maps NORMAL/OVP/OCP/OPP correctly; OPP is never flattened into two false binary bits.
5. Direct internal register-16 probe remains fresh and the live-adopt command refuses stale/nonzero protection code.
6. With external Output ON and healthy positive V/I/OVP/OCP, D061 preflight is read-only.
7. Live-adopt changes edge ownership/generation only; Output/V/I/OVP/OCP are byte-for-byte/readback unchanged.
8. Positive ACK requires generation change, armed healthy state, fresh direct Modbus and near-full 900 s remaining lease.
9. Generation race or ambiguous ACK enters containment and never silently claims PB ownership.
10. Raw protection loss immediately after ACK does not reopen heartbeat authority.
11. Raw protection loss/OPP after successful adoption makes managed runtime fail closed to verified OFF.
12. Out-of-band V/I/OVP/OCP increase above adopted authority makes managed runtime fail closed; downward changes only ratchet authority down.
13. Operator Stop uses verified OFF and never the legacy power-toggle path.
14. Process kill/restart while adopted never resumes live authority and completes verified-OFF containment.
15. Only after the D061 bench passes may D062 `MIX_ADOPTED` use this ownership-transfer primitive.

Until those physical gates pass, CI success means **software-contract PASS only**.

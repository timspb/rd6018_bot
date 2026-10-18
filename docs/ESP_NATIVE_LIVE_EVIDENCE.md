# Current physical evidence — ESP Native API first

Status: **CURRENT operational authority**, effective 2026-10-18.

## Non-negotiable operator instruction

**БРАТЬ АКТУАЛЬНЫЕ ДАННЫЕ С ESP.**
**GET FRESH PHYSICAL DATA FROM ESP NATIVE API, EVERY TIME.**

node104 is the production bot host. The physical ESP device used by the bench
was reached as `192.168.1.28:6053` (resolve the target against current
configured node identity; do not assume its address is permanently fixed).

Two paths to the same RD6018 via ESP exist:

1. Direct ESPHome Native / Noise API (`esp_direct`, `aioesphomeapi`):
   **authoritative for live physical observations**.
2. ESP -> HA102 -> bot via HA REST: **secondary, potentially delayed**;
   useful for consistency checking only.

Never promote the secondary path, a Telegram UI value, cached sample, historical
JSON, previous report, or the ability to connect to port 6053 into fresh
native physical proof.

## Required observation on EACH live preflight

Actively acquire new ESP Native callbacks using existing project adapters.
Read and record with ESP identity, source, native info/state type,
callback/subscription timestamps, freshness/age and acquisition time:

- Physical RD6018 Output state, **R18** (`output_state_code_v2`, `switch`)
- Actual measured RD6018 voltage and current; battery voltage
- Programmed **Vset/Iset**, **OVP/OCP**, protection **R16**
- Edge lease **armed, generation, remaining, TTL**, Modbus age
- **trip, boot quarantine, autonomous/ownership** flags
- Service/session identity separately from node104's read-only service/journal

Native inventory `ButtonInfo(safety_lease_renew)` proves that the entity
exists; it does **not** confirm that a renew was sent or acknowledged.
ACK requires fresh generation/armed/remaining readback. Port reachability
only proves TCP connectivity.

## Timing and OFF validation

- Read ESP immediately before START, after every relevant state change, before
  any production deployment/swap, and after STOP. Re-read for each attempt.
- For post-command OFF receipts use the existing D089 proof rule: fresh
  post-completion Native `SensorState` callback for R18, bounded freshness
  (the accepted receipt uses age <=8s), actual zero Output/U/I, correct
  identity/source, timestamp strictly newer than command completion.
- Validate freshness rules specific to each signal; Modbus edge age must
  respect the existing 20s maximum. Don't replace this with guessed clocks.
- Versioned deployment needs independent new pre-stop and post-service-stop
  evidence within the canonical D090 transaction proof windows. Reusing one
  sample for both phases is not proof.
- HA102 can supplement a report; a conflict is evidence to investigate,
  NOT permission to trust HA over ESP.

## Existing access and execution path

Use **existing** `runtime.physical` ESP-direct connector,
`aioesphomeapi`, `tools/node104_d091_physical_proof_collector.py` and
`tools/node104_d106_live_observer.py` on the authorized host/runner. Discover
the deployed configuration and keys through already permitted secure
interfaces; do not commit, echo, screenshot, or copy secrets into reports.
The current production host is node104, not HA102 or node101.

Do not claim that a missing Telegram `cua` handler makes Native telemetry
unavailable; UI access and Native read-only observations are independent.
A particular shell/SSH safety restriction must not be bypassed under a
different wrapper. If available approved tooling really cannot read ESP,
state the precise limitation: **ESP ACCESS BLOCKED**. Then do not touch
production, energize Output, or claim a current physical state.

Reading ESP is not the same as issuing commands. ESP buttons, Modbus writes,
lease renew/disarm, Output ON/OFF and setpoint changes remain under the
single established bot/ExecutionPort owner. A read-only observer must not
acquire actuator authority.

## D109 MAIN Guard acceptance

1. New direct ESP preflight: real R18 OFF, measured U/I=0, R16/OVP/OCP,
   battery, edge-lease and controller/session state with timestamps.
2. Existing bot START only; prove **Native** lease generation increase,
   armed=true and positive readback before Output ON.
3. Real 1800 s of physical MAIN Output ON; inspect measured current,
   decreasing Iset/OCP and durable journal/readback without time shortcuts.
4. Existing bot STOP; capture a new direct ESP OFF + zero U/I receipt.
5. Report exact times, fresh Native proof, secondary HA comparison, result
   PHYSICAL PASS / FAIL / BLOCKED and the precise reason.

This document authorizes no new actuator and overrides no existing safety
gates or immutable old-release pins.

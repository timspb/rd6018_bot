# D061 — raw protection evidence-loss: physical acceptance PASS (2026-10-14)

**Scope.** One bounded electrically real RD6018 negative scenario: `d061_fault_raw_protection_unavailable`, an **in-process unavailable raw-protection evidence** injection following successful HANDS_OFF → PB_MANAGED takeover. This is **not** a forced real register-16 OVP/OCP/OPP trip.

## Physical result

- Node104, Leoch Ca/Ca 72 Ah. Preserved Vset **13.57 V**, Iset **0.10 A**, OVP **14.07 V**, OCP **0.20 A**.
- Real output ON: **13.09 V / 0.09 A**; subsequent samples 13.10–13.11 V / 0.09 A.
- Battery probe **23 °C**, RD6018 block/PSU probe **29–30 °C**. These are distinct sensors; intrinsic block cutoff remains **55 °C**.
- Adopted `PB_MANAGED` with **19/19 named post-adoption predicates PASS**; only then executed one typed synthetic loss of raw protection evidence.
- Typed result: `ok=true`, `contained=true`, `output=off`, `lease_armed=false`, `adoption_state=completed`. Canonical safety rejected missing protection evidence and issued verified OFF.
- New post-command output heartbeat plus independent HA102 and native ESP128 confirmed OFF. Output converged to **0.00 V / 0.00 A**; physical raw protection returned NORMAL. All V/I/OVP/OCP readbacks retained their previous values.
- Lease generation sequence: preflight **26**, armed **27**, HANDS_OFF release **28**, final disarmed **29**. Software ownership retired (`manual_state=stopped`, `adoption_state=completed`); acceptance poller stopped; containment and production restoration PASS.
- Original production service active before (PID 55291) and after (new PID **56233**); `NRestarts=0`. Post-run independent read-only audit found exactly one production bot, no acceptance executor, OFF / zero output, lease disarmed, raw protection NORMAL, root-owned 0600 lock, and production physical-test socket disabled.

**Canonical source:** `594a386e2b9fdd6bde9ebb15a5dfab30155291d6` with 875/875 verified source-file digests; source manifest SHA-256 `8e31b6d11c1fa2c9acbf038cd79e4f0adee7c011f8026656987c8891651ca288`. The reviewed supplemental overlay and sole enumerated fault operation were enforced by the physical Windows/SSH runner. Both inner acceptance receipt and outer runner reported **PASS**, with runner exit code **0**.

**Evidence:** the byte-retained HOME-PC acceptance JSON has SHA-256 `c50cb4186ad4a52aa68b01cc7b33a247ac844ad4a331090e5f373a5881ab77c2`; the final independently observed read-only audit SHA-256 is `0baddbee47be77e56b8b0b055e5b9c8c67f68603137d688256af0d5263408030`. Machine-readable non-secret summary: [D061_RAW_PROTECTION_EVIDENCE_LOSS_PHYSICAL_PASS_2026-10-14.json](D061_RAW_PROTECTION_EVIDENCE_LOSS_PHYSICAL_PASS_2026-10-14.json). Original archived locally at `E:\CODEX\RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE\D061_RAW_PROTECTION_PHYSICAL_PASS_20261014.json`.

Detailed operator-independent receipts are indexed in [issue #68](https://github.com/timspb/rd6018_bot/issues/68#issuecomment-6164823094).

## Delimited acceptance

**CLOSED — this synthetic in-process raw protection evidence-loss case only.** Actual physical hardware register-16 OVP/OCP/OPP assertions, other stale source conditions, ACK/generation races, out-of-band authority changes, and adopted bot kill/restart remain **OPEN**, requiring separately reviewed and independently proven physical runs. Do not extrapolate this PASS to the rest of the fault/restart matrix.

No ESP OTA, no 900-second endurance repetition, and no production architecture rewrite were performed.

# D061 supervised transient 900-second physical checkpoint — 2026-10-13

**Status: physical transient / lease endurance PASS; complete bot-level D061 acceptance remains OPEN.** This is a bounded test result, not approval to activate production bot/ESP firmware, D062 MIX_ADOPTED, D064 or D065.

## Physical execution and measured evidence

A supplemental, guarded, isolated D061 transient acceptance window was run against the real RD6018/Leoch 72 Ah Ca/Ca supervised bench, using exact Python candidate `19577fcaa220cafbc90fa69611ac925b7c47c21d` and a temporary overlay. **The existing production tree, service unit, persistent runtime and firmware were not replaced.**

- Guarded requested setpoints: **13.57 V, 0.10 A**; OVP **14.07 V**, OCP **0.20 A**. Electrical emergency protections remained enabled.
- Configured timed acceptance: **900 seconds**. Collected **449 monitoring samples** covering **899 seconds from first to last sample**; acceptance runner and transient exited with status **0** and temporary stage cleanup succeeded.
- During monitored ON: measured output voltage **13.19–13.32 V**, current **0.09 A**.
- Internal RD6018 temperature: max **38 °C**. External battery sensor `temp_ext_v2`: max **24 °C**; internal and external temperatures must not be conflated.
- Raw hardware protection status: `0 / NORMAL` throughout observed samples. Edge lease stayed armed and untripped without boot quarantine. Maximum reported Modbus age **5.754 seconds**.
- Guarded finalization commanded OFF. Independent HA102 and ESPHome Native API checks then agreed on **Output OFF, 0.00 V, 0.00 A**, lease disarmed with trip/quarantine clear.
- Production service restored to `active` with original `bot.py` runtime; contemporaneous MainPID **49951**, `NRestarts=0`, one bot process. A subsequent independent read-only snapshot at **2026-10-12T15:56:04Z** still showed both HA and ESP Output OFF, 0.00 V/A, battery voltage around **13.15 V**, protection NORMAL and unarmed lease, service active.

The operator previously confirmed an operable emergency cutoff, installed battery temperature sensor, identified Leoch battery and active bench supervision. Evidence comes from the local supervised runner's time-series and post-window independent readbacks. This is **not** a claim of laboratory-calibrated metrology, a full independent firmware attestation, or hardware fault-injection PASS.

Local private evidence (not committed): `E:\\CODEX\\RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE\\d061-live-900s-retry-evidence.json`, `D061_TRANSIENT_900S_RESULT_20261013.md`, `final-live-readback.json`. A prior attempted 900s window failed because a supplemental ESP read-only output method was unavailable; it is not counted as this PASS. The corrected guarded overlay SHA-256 was recorded as `c0998a24ee2c0a84b3d309f4ec064236a0c2b0cc63e55dbd1a1b94d1d064d02c`.

## Software and firmware evidence boundary

- Supplemental acceptance overlay regressions: **26/26 PASS**.
- Exact-candidate D061 restart/OFF and HANDS_OFF retirement regressions: **11/11 PASS**.
- Additional focused live-adoption tests: **59/59 PASS**. Earlier exact-candidate full suite: **1617 PASS**; sink guard: **38 PASS**. None substitutes for hardware acceptance.
- Exact candidate's tracked ESPHome source was locally compiled using ESPHome **2026.8.2** and **example/dummy secrets**. Artifact `rd6018-controller-v2-ec8e341.bin`, SHA-256 `8d8422e2119dab0293f20a4a9363dda879d941b50e7e2f7df34bf15e5a0c3bc0`. **Not a production firmware image; not flashed.**
- The currently installed ESP reports project version `2.2-autonomous-authority`, but the running binary's exact digest was **not independently attested**. Production deployment of exact matching firmware and bot was **not** performed.

## Gates still OPEN

The firmware's corrected force-updated telemetry / `Output State Code V2` must be verified on the exact flashed image. The supervised transient does not exercise real **bot-level HANDS_OFF → PB_MANAGED** positive takeover. The next bounded scenario is the reviewed 20-second acceptance-only pipeline:

1. Independent, fresh OFF and normal-protection preflight; no competing controller or poller.
2. Canonical guarded safe program ON, deliberate release to HANDS_OFF, then typed bot `d061_adopt_battery` with the exact staged candidate.
3. Verify generation, raw protection, lease, fixed setpoints and no unintended Output transition across adoption.
4. Typed verified Stop, independent OFF, lease disarm and original service restoration.

**Do not execute** this flow before correcting/validating the supplemental takeover OFF-proof's native physical-output readback and failure containment. In particular, a lease-only `ESPHomeTransport.get_entity_state()` call is not sufficient to read the native `Output State Code V2`; the read-only physical sensor must be validated through its dedicated interface. Preserve normal 12-second transition dwell and immediate emergency OFF.

The complete D061 checklist in [D061 managed adoption](D061_MANAGED_LIVE_ADOPTION.md) remains authoritative, including raw register-16 OVP/OCP/OPP rejection, post-ACK evidence loss, out-of-band authority increase, downward ratchet, Operator Stop and bot restart containment. D064/D065 reboot/autonomous cases and D062 Mix adoption are not inherited from this test.

**Status: 900-second transient physically PASS; full D061, firmware activation and production rollout HOLD.**

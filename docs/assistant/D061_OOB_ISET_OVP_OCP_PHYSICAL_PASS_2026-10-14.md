# D061 — three additional real OOB authority-increase physical PASS receipts

**Date:** 2026-10-14 UTC. **Bench:** physical RD6018, real Leoch Ca/Ca 72 Ah battery, node104; native ESP128/HA102 readbacks; firmware `2.2-autonomous-authority` unchanged.

**Result:** **PHYSICAL PASS** for each externally raised **OVP, Iset, and OCP** after a proven PB_MANAGED live adoption. Together with the previously merged [Vset physical PASS](D061_OOB_VSET_PHYSICAL_PASS_2026-10-14.md), **all four positive-direction out-of-band authority mutation classes are now physically accepted**. These tests **do not** constitute actual electrical OVP/OCP/OPP protection trips. They do not close active adopted-bot SIGKILL/restart.

## Pinned source, independent fixture, and safety

- Exact canonical code commit: `aecf602f521025cc4ce1348e96a79bf4548e6f19`; immutable Git archive **899 files**, manifest SHA-256 `46c890c70c57e2e665e9fd732d8b357ab557468c192a396d1eb7d39c78c4dc68`, canonical source tar SHA-256 `40c17f305b72028dc96c19f524ca48c24eed00ebcf67eac106729c8aee4da197`.
- All three independent reviewed acceptance-only override pairs were byte-hashed by Windows before packaging, validated with source manifest, and admitted by node104 **899/899 pairing PASS**, global root mode-0600 acceptance lock PASS, and real native OFF PASS. No production source or firmware was deployed.
- OVP `pairing.py` SHA256 `d9113f1dfb595fa3550926255ce1b020a6a337b3bf24500eeec08c6186b69f58`; `takeover.py` `93800212336058370906b67eaa51ed8da8b6724b85154f2b041766b849e4a883`. Hardware-inert suite **29/29 PASS**.
- Iset `pairing.py` SHA256 `7404c6e8850529d8a11b8b60be73d4c348ac69b9a1a8a95269a4fac89f81f1d7`; `takeover.py` `da8d1fccdebe30b04a19ad25ee8f20688dc9f7b0d2b6cb1d2a5734414ce0e106`. Hardware-inert suite **29/29 PASS**.
- OCP `pairing.py` SHA256 `0c9b672b4b22ad1d58acfb3aab880a738ea41974bd1a41ff1173f2a0f2e0ff4f`; `takeover.py` `6522827da2ef180f6891909f171819611c161c903ad30c83b0275ad12adde136`. Hardware-inert suite **29/29 PASS**.
- Before each physical mutation: independent OFF, hardware readback of **Vset 13.57V, Iset 0.10A, OVP 14.07V, OCP 0.20A**, healthy unarmed native lease, raw protection NORMAL, global owner lock; then conservative ON and independently proven `PB_MANAGED` live adoption **19/19 predicates PASS**.
- Each mutation was performed **outside the adopted bot** through a separate HA REST client to exactly one mapped number entity, and positively observed using the independent **native ESP128 setpoint mirror**, rather than a software fake or mere command ACK. The adopted coordinator's specific authority-increase condition was checked. Success required dual HA102/native ESP128 fresh Output OFF = **0V/0A**, verified lease disarm, restored original setpoint only after OFF, retired ownership, no acceptance poller, and restored exactly one production process.

## Actual hardware observations

| Check | OVP | Iset | OCP |
|---|---|---|---|
| Injected operation | `d061_oob_ovp_raise` | `d061_oob_iset_raise` | `d061_oob_ocp_raise` |
| Physical external setpoint readback | **14.07 → 14.15 V** | **0.10 → 0.18 A** | **0.20 → 0.28 A** |
| Transaction receipt UTC | **14:18:07.203605** | **14:23:51.696384** | **14:27:45.822808** |
| Real adopted observer state | `failed/failed` | `failed/failed` | `failed/failed` |
| Verified native edge generation | **46→47 armed→48 release→49 disarmed** | **49→50 armed→51 release→52 disarmed** | **52→53 armed→54 release→55 disarmed** |
| HA + native ESP verified OFF | **0V / 0A** | **0V / 0A** | **0V / 0A** |
| Return of original field *after* OFF | **14.07 V PASS** | **0.10 A PASS** | **0.20 A PASS** |
| Physical transaction result | **PASS** | **PASS** | **PASS** |
| Edge lease disarmed / ownership safe / acceptance poller stopped / production restored | **all true** | **all true** | **all true** |
| Raw protection / temperatures | **NORMAL; PSU 30°C, battery 23°C** | **NORMAL; PSU 30°C, battery 23°C** | **NORMAL; PSU 30°C, battery 23°C** |

**Individually pinned original evidence files on Windows; SHA256 of the exact original bytes:**

- OVP: `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-oob-ovp-v2-20261015-001808.json` — **`0583ad8b7b4ab4727db7de2146416c51674aa20327efa6991d4c006a1b6eeb63`**. Parsed snapshot: [OVP JSON](D061_OOB_OVP_PHYSICAL_PASS_2026-10-14.json).
- Iset: `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-oob-iset-v2-20261015-002352.json` — **`aa248b6cb3392c5eec9f618fdeeccf8c941dc3821e7cba2e6ad82f7c980bcbd0`**. Parsed snapshot: [Iset JSON](D061_OOB_ISET_PHYSICAL_PASS_2026-10-14.json).
- OCP: `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-oob-ocp-v2-20261015-002747.json` — **`8a601d9bbaffcaec9ec11e569944cc80d20b8d9a7541f090bf2ee977af2f8bdb`**. Parsed snapshot: [OCP JSON](D061_OOB_OCP_PHYSICAL_PASS_2026-10-14.json).

## Failure history, no suppressed cases

Earlier OVP run with the first readback executor at **2026-10-14 14:10:10 UTC** correctly raised the real OVP register to 14.15V, reached actual `failed/failed` and canonical Output OFF, but the **immediate separate fresh dual-source OFF observation failed its timing window**. It correctly recorded **FAIL**, did not auto-resume production, and left OVP at 14.15V with the output physically OFF. Fresh independent Windows-pinned SSH preflight then proved both HA and native ESP **OFF 0V/0A**, lease disarmed, no trip and normal protection; an OFF-only bounded actuator recovery returned the original **OVP 14.07V** and independently rechecked both sources and production ACTIVE. The separate reviewed v2 scenario adds bounded fresh dual-source report acquisition, real-only; **29/29 offline tests** passed before repeating physical OVP and obtaining the complete PASS above. Preserve the original FAIL receipt and its recovery evidence separately; never rewrite FAIL as PASS.

## Final independently verified node104 state

At **2026-10-14 14:28:27 UTC** after all three accepted tests, a new pinned-SSH read-only probe independently verified:

- Original `rd6018-bot.service` **ACTIVE**, single PID **59725**, `NRestarts=0`, no extra acceptance processes, physical-test socket ABSENT and root 0600 global lock present.
- **Both HA102 and native ESP128 VALID**, Output OFF **0.00V / 0.00A**, setpoints **13.57V / 0.10A / OVP14.07V / OCP0.20A**.
- Edge safety lease **DISARMED**, not tripped, not boot-quarantined; raw hardware protection **NORMAL**.
- PSU block **30°C**, battery **23°C**. No firmware, actual installed bot code, or production configuration modification.

## Remaining D061 acceptance

- **OPEN / safety HOLD:** genuine physical `SIGKILL` of an **energized PB_MANAGED adopted-session bot**. The earlier true production `SIGKILL` at OFF and systemd restart proved only the **OFF-state restart** boundary; 900s native edge lease TTL is insufficient to protect against abrupt death during active charging without an **independent, pre-armed root-owned OFF watchdog** that owns the single global lock throughout and can retire the lease and prove fresh physical OFF without the killed process.
- **OPEN:** actual electrical register-16 OVP, OCP and OPP trips. Those require **an isolated, supervised bench fixture and load**, not deliberate fault overvoltage/overcurrent against the connected Leoch battery. Do not conflate these with the successful OOB *upward setting-change detection* checks.

This change archives evidence only. It authorizes no change to installed production code, firmware, physical limits, or global gates.

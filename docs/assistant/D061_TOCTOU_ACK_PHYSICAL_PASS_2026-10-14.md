# RD6018 D061 — physical TOCTOU + ambiguous edge ACK acceptance PASS

**Physical date:** 2026-10-14. **Node:** node104 / RD6018 / Leoch Ca/Ca 72 Ah.  
**Canonical exact-source SHA:** `aecf602f521025cc4ce1348e96a79bf4548e6f19`.  
**Firmware:** `2.2-autonomous-authority`, unchanged. **Production** untouched except bounded supervised test handovers and verified restore.

## Why a retry was necessary

A **failed physical first TOCTOU run** at 2026-10-14 11:10:20 UTC used pinned source `594a386e2b9fdd6bde9ebb15a5dfab30155291d6`, containing older `physical_test_control.py` fault hooks with a globally consumed `read_count`. During the race, the wrong asyncio task could consume the injected second read; actual return: `TOCTOU injection unexpectedly completed adoption`. The runner recorded **FAIL**, independently proved OFF and lease disarmed, refused to auto-restart production while ownership remained unproven, and original production was subsequently safely restored with an independent Windows→node104 pre/post audit. Original first-failure Windows receipt: `d061-race-20261014-211021.json`, SHA-256 `1da2a9a02faf6e0bc679b5a56658a328f222489101307a42fc72b1dba219967a`. This failure must not be overwritten or represented as PASS.

The subsequent exact-source `aecf602` includes **task-local** injected TOCTOU and ambiguous ACK boundaries. Source manifest: 899 Git-archive files, SHA-256 `46c890c70c57e2e665e9fd732d8b357ab557468c192a396d1eb7d39c78c4dc68`. Canonical tar SHA-256 `40c17f305b72028dc96c19f524ca48c24eed00ebcf67eac106729c8aee4da197`. A separately byte-pinned, two-file acceptance-only overlay replaces `tools/acceptance_guard/pairing.py` and `tools/acceptance_guard/takeover.py`; the former authorizes the 899-file exact source and these precise override paths (its own digest is externally pinned by the Windows host and archived attestation). Their digests:

- `pairing.py`: `7f7ef66ad562216ec5ee9053a6dcf3b29f197cc613b00ca723de35eb6e8713c8`
- `takeover.py`: `4cb491220f408a5878718380b917cf367783b8b216391fa5fe3116a97aa78764`

Windows host-side offline archive verification **PASS**, target node104 **pairing 899/899 PASS**, root-owned global gate **PASS**, independent HA102/native ESP128 OFF preflight **PASS**, production single-owner invariant **PASS**. The previous 875-file accepted runner/manifest was **not altered**.

## Actual physical results

| Check | Pre-command TOCTOU | Ambiguous ACK |
|---|---|---|
| Result | **Physical PASS** | **Physical PASS** |
| Native receipt UTC | 11:43:44.865 | 11:45:49.074 |
| Injected operation | `d061_fault_toctou_precommand` | `d061_fault_ambiguous_edge_ack` |
| Generation before → after fault | **34 → 34**, unchanged | **36 → 37**, advanced |
| Command may have executed | **false** | **true** |
| Production response | Pre-command fingerprint mismatch rejected; `hardware_writes_injected=0`; canonical guarded fault OFF | Actual edge adopt command issued, positive ACK hidden for task-local window; ambiguous command classified and canonical OFF containment executed |
| Energized measurement | approximately 13.09 V / 0.09 A | approximately 13.10 V / 0.09 A |
| Raw protection | NORMAL (code 0) | NORMAL (code 0) |
| Battery and PSU temperature | 23 °C / 29 °C | 23 °C / 29–30 °C |
| Independent physical OFF | PASS, 0.00 V / 0.00 A | PASS, 0.00 V / 0.00 A |
| Edge lease | DISARMED; generation 34 | DISARMED; generation 37 |
| Ownership safe | true | true |
| Acceptance poller stopped | true | true |
| Original production restored | true | true |

**Original Windows transaction receipts (SHA-256 of source bytes before GitHub formatting):**

- TOCTOU: `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-race-20261014-214346.json` — `b4af68a951ec8ea66f21d6e7779291b829633cd5ff9f337ccee882e8b4cf4bba`
- Ambiguous ACK: `C:\Users\HOME-PC\d061-takeover-evidence\d061-aecf-race-20261014-214550.json` — `8dff41574044f0fdd2457bb243dbee4057ad36c6b768f540963bb3e24a71596c`

Parsed transaction receipts are also archived in adjacent [TOCTOU JSON](D061_TOCTOU_PHYSICAL_PASS_2026-10-14.json) and [ambiguous ACK JSON](D061_AMBIGUOUS_ACK_PHYSICAL_PASS_2026-10-14.json).

## Independent post-test production verification

Post-ACK pinned-SSH, independent HA102/native ESP128 read-only probe at **2026-10-14 11:46:09 UTC**:

- Output OFF from both transports, **0.00 V / 0.00 A**; native lease **unarmed**, no trip or boot quarantine; raw protection **NORMAL**.
- Setpoint readbacks unchanged: Vset 13.57 V, Iset 0.10 A, OVP 14.07 V, OCP 0.20 A.
- Battery temperature 23 °C, PSU block 30 °C.
- `rd6018-bot.service`: ACTIVE, exactly one bot process PID **57146**, `NRestarts=0`; no orphan acceptance process; physical test socket absent; node104 global lock root mode 0600.
- No changes to installed firmware or production source.

## What remains OPEN

These two **D061 edge race** physical scenarios are now accepted. The following physical classes are **not** covered by them: actual register-16 OVP, OCP, OPP electrical assertions; external out-of-band V/I/OVP/OCP manipulation while adopted; and adopted-bot kill/restart. Their own hardware fixtures, safe operation/containment criteria, and distinct physical receipts are still required. Do not extrapolate this PASS to those cases.

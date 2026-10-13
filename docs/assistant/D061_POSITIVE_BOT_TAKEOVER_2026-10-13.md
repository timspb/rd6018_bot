# D061 — positive bot-level takeover: physical PASS (bounded)

Date: **2026-10-13**. Exact canonical source: `19577fcaa220cafbc90fa69611ac925b7c47c21d`. Original source manifest SHA-256: `cb179bafaa8444b900e93b5e132aef0e02d1d9e4c28a41136c8f2a9d2fce31dc`; **873/873 original files**; additional guarded acceptance overlay attested separately. Installed ESP reports firmware project `2.2-autonomous-authority` (compiled 2026-10-11); **no OTA performed in this acceptance**.

## Bounded physical result

**Positive HANDS_OFF → PB_MANAGED → verified OFF → restore production: PASS** on a real RD6018 with saved **Leoch Ca/Ca 72 Ah** battery. The root-owned node104 receipt reports `result=PASS`, `containment_complete=true`, `ownership_safe=true`, `independent_output_off=true`, `edge_lease_disarmed=true`, `acceptance_poller_stopped=true`, and `production_restored=true`.

- Canonical `d061_adopt_battery`: `adopted=true`; latest post-adoption proof: **19 named checks, all true**. Adopting produced no V/I/OVP/OCP rewrite. Edge generation advanced; lease armed healthy before typed Stop.
- Program: **Vset 13.57 V / Iset 0.10 A / OVP 14.07 V / OCP 0.20 A**.
- Real ON readback: **13.10–13.12 V / 0.09 A** across four live samples; raw protection `0 NORMAL`.
- External **battery temperature 24 °C**, internal **RD6018 block temperature 30 °C**. These are distinct sensors, never interchangeable.
- Typed `d061_verified_stop`: `ok=true`, `stopped=true`, `output=off`.
- Canonical fresh post-OFF confirmation log: `Output OFF confirmed: source=output_state_code_v2 ... post_command=true`; `Output OFF verification complete`; `Edge safety lease disarm confirmed`.
- Final independent HA102 + ESP128: Output OFF, 0 V, 0 A, lease disarmed, no trip/quarantine, protection NORMAL.
- Original production service `rd6018-bot.service`: **active, PID 54230, NRestarts=0**, one bot, zero acceptance processes at independent readback on 2026-10-13 12:57:54 UTC.

## Evidence and Windows runner false negative

The physical acceptance process on node104 exited after writing a root-only mode-0600 evidence JSON. Its transaction status was **PASS**. The Windows wrapper initially exited **1** with `[Errno 13] Permission denied` when trying to read that root-owned receipt through non-root SFTP. This is an evidence-transfer defect, **not a physical D061 failure**. A separate pinned SSH **sudo read-only** retrieval validated the successful receipt without changing on-disk file rights. Its local path:

`E:\\CODEX\\RD6018_V3_SAFE_ACCEPTANCE_LUNA_EVIDENCE\\d061_positive_verified_20261013.json`

Recovered receipt SHA-256 (pretty-printed local JSON):
`42fc04e64aad7c266a3565f13bb27f9a9a8ed98a6c693d48976a83959ca3ff9f`.

Remote original stage retained for audit:
`/tmp/rd6018-d061-takeover-f08e13e9f62847438812edcddf416788/state/d061-takeover-result.json`.

Wrapper corrected to retrieve via the pinned SSH channel and `sudo -n cat`; no chmod/chown to weaken evidence security. No repeat hardware cycle is required to fix the original Windows exit code.

## Causes and fixed acceptance contracts

Previous failures were identified and fixed without changing ESP firmware: stage-local concurrent owners → node-wide root-owned flock, ambiguous or delayed OFF confirmation → real ESP native callback timestamp preserved in source metadata (no synthetic freshness), and a false `asyncio.wait_for` at precisely the 20-s boundary → bounded hold margin. The prior root-owned evidence and earlier failed test stages were retained separately and remain historical FAIL results, **not overwritten**.

Offline focused tests: 135/135 PASS for guarded D061 and native heartbeat checks prior to latest launch. Additional wrapper syntax and stage-pairing tests: 9/9 PASS. Real node104 prepare-only: locked sole owner, verified fresh independent OFF, 873/873 exact source pairing, approved supplemental overlay, unchanged production PID.

## Offline negative/fault/restart matrix (2026-10-13)

After the bounded hardware PASS, **65/65 hardware-inert tests PASS** across `test_d061_restart_off_audit`, `test_rd_managed_adoption`, `test_edge_live_adoption`, `test_physical_test_fault_injection`, `test_esphome_live_adoption_contract`, `test_runtime_edge_lease`, `test_physical_test_source_faults` and `test_rd_live_adoption_zero_protection`. These use fake transports/controllers, not hardware fault injection, so they do **not** close the physical restart/fault gates below.

The corrected Windows root-only receipt path also passed three independent hardware-inert checks (approved read, unsafe stage rejection, invalid result rejection). Source-level `git diff --check` passed. Latest read-only live check at 2026-10-13 13:10 UTC: HA and ESP both Output OFF, 0 V/0 A, lease disarmed and NORMAL protection; original production PID `54230`, `NRestarts=0`.

## Scope boundary: what is NOT yet accepted

**The successful positive D061 smoke does not close the full physical fault/restart matrix.** Independently pending:
- Raw register-16 OVP/OCP/OPP negative hardware fault injection and stale/unknown protection rejection.
- Ambiguous edge ACK/generation race and post-ACK raw protection loss on the real hardware.
- Out-of-band V/I/OVP/OCP increases and the allowed downward authority ratchet under an adopted bot session.
- Kill/restart behavior of the adopted bot and independent verified-OFF/recovery matrix.
- Any full production migration from the original bot runtime; no firmware OTA or production code replacement occurred in this test.

Existing 900-second physical transient endurance remains PASS separately; do not repeat solely on account of these acceptance-harness fixes. No high-voltage charging, D062 MIX_ADOPTED, or D064/D065 production acceptance is implied.

**Conclusion:** bounded D061 bot positive physical smoke **PASS**; complete D061 hard-fault/restart acceptance **OPEN**; original production **restored**.
# B1051 — node104 fresh direct ESP Native + HA102 read-only preflight, 2026-11-27

**Decision: NATIVE BASELINE OBSERVED; B1020 Gate 0/1 overall BLOCKED; P3/P8 HOLD.** No physical test or release was initiated.

## Acquisition and provenance

- Time: `2026-11-27T01:55:32.716Z` (Unix epoch `1795744532.7168334`), node104 live read-only observation by controlling HOME-PC MCP.
- Authorized existing saved WinSCP `104` connection. Non-persistent in-memory `python -c` with `PYTHONDONTWRITEBYTECODE=1`, installed `ESPHomeTransport` and `HA102Transport`, D091 fresh typed callbacks and D106 firmware identity validator. **No script/file was copied to node104, no control call, no configuration, service or device change.**
- ESP identity: `timspb.rd6018-pb-recovery-v2`, `2.3-ha-canonical`, `rd6018-controller`, `esp01_1m`. One physical Native device in the inventory; default configured connector `esp_direct`. Source `esp_native_api` (new subscription); all shown native callback ages <0.56 s. R18, U and I each typed `SensorState`, separate from writable `NumberState`.
- Service before and after remained `active`, MainPID `332973`, one bot process. Installed node remains D144 stable baseline (slot 22, `76df9ecd...`), **not installed B1048 candidate**.
- Read-only on-disk production admission: `charge_session.json` CLEAR under D091 `_session_state`; `session_recovery_quarantine.json` CLEAR under D091 `_journal_state`. These checks did not write or clear files.

## Fresh Native and secondary HA observations

| Signal | ESP Native | Native age (s) | HA102 secondary | HA age (s) |
|---|---:|---:|---:|---:|
| R18 Output | 0 / OFF | 0.0549 | 0 | 3.5 |
| Measured U | 0 V | 0.0013 | 0 V | 4.1 |
| Measured I | 0 A | 0.0013 | 0 A | 4.1 |
| Raw R16 | 0 | 0.556 | 0 | 3.5 |
| Autonomous | false (`BinarySensorState`) | 0.558 | false, **STALE** | **14,460** |
| Programmed Vset | 2.40 V | 0.556 | 2.40 V | 4.1 |
| Programmed Iset | 1.70 A | 0.556 | 1.70 A | 4.1 |
| Battery voltage sensor | 0.01 V | 0.502 | — | — |
| Internal temperature | 30 °C | 0.556 | — | — |
| External temperature | 25 °C | 0.232 | — | — |
| Lease armed | false | 0.558 | Native only | — |
| Lease remaining / TTL | 0 / 900 s | 0.350 | Native only | — |
| Lease generation | 0 | 0.350 | Native only | — |
| Lease tripped / boot quarantine | false / false | 0.558 / 0.557 | Native only | — |
| Modbus edge age | 3.788 s | 0.350 | Native only | — |
| OVP / OCP observed readback | 0 / 0 | 0.556 | — | — |

Native measurement callback monotonic timestamps: R18 `5348450.323558059`, U `5348450.377103429`, I `5348450.377173327`. Installed old D091 callback wrapper did not supply `connection_generation`; **do not invent one**. Separate direct source and freshness, actual firmware project/version, current readings and physical trace are grounded. Raw OVP/OCP values are read-only diagnostics, not software protection authority. Battery 0.01 V **does not establish an appropriate connected charging load**; do not assume or start charging.

## Root cause of installed D106 rejection

The installed `tools/node104_d106_live_observer.py` without the newer `--phase-observation` CLI option previously returned `ProofError: HA last_reported source is stale`. Current direct HA REST read shows **only the HA `autonomous` entity at age 14,460 seconds (~4 h 1 m)**, despite `autonomous=false` being **fresh and typed in Native**. The other six HA fields were recent (3.5–4.1s), within D106's 8s source bound. This explains the D106 strict dual-source failure: the readonly `project_off` policy requires independently fresh HA `autonomous`. This record does not weaken that validator or label a stale HA record fresh. No evidence of an ESP Native failure. Root cause for **why** HA's autonomous entity is not republished is not yet independently established; do not infer ESP or HA transport failure from an unchanged binary value.

## Decisions and next finite steps

- **B1020 Gate 0 BLOCKED** for an actual test: no separately approved exact-candidate live bench/load scenario or operator present. B1048 source `b016e0ad...` passed offline checks, but is not installed on this node.
- **Gate 1 NATIVE physical subsection OBSERVED**, including source, firmware, freshness, R18 OFF, 0 V/0 A, raw R16, all lease fields, temperatures and clear session/quarantine. **Full dual-source Gate 1 BLOCKED** by HA autonomous age and unknown supervised battery/load scenario. This is not a D089 post-command OFF receipt because no command happened.
- **Gates 2–5 NOT RUN**: do not energize Output, program V/I, change safety lease, inject OPP/R16 or simulate lease expiry without exact-source, approved supervised bench. The D090/D138/D142/D145 source-paired node104 release and P8 remain HOLD.
- Candidate source already includes separate opt-in D106 `--phase-observation` that deliberately returns Native observation without claiming D090 dual-source OFF proof; installed baseline lacks it. No firmware flash or deployment was performed here. Resolve D106 HA autonomous evidence strategy only by an explicitly reviewed source contract, preserving fail-closed Native and preventing stale/contradictory HA fields from being misrepresented. **Do not change B1048 frozen archive/source SHA in place.**
- Original canonical P0–P9 **99/104**: P3 3 HOLD, P8 2 HOLD. The read-only acquisition closes zero physical checkboxes.

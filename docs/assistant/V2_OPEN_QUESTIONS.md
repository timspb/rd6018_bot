# V2 Open Questions

> Only unresolved strategy/product questions live here. Resolved behavior belongs in `V2_DECISION_LOG.md`.

Q001, Q002, Q003, Q006, Q007, Q008, Q009, Q010 and Q012 are intentionally retired: initial PREP handling, Manual identity/re-authorization, AUTO Manual-OFF semantics, post-heavy-recovery rest authority, intent semantics, 72h Main fallback, AGM recovery policy, diagnostic restart persistence and SG access/correction/prompt policy now have accepted/implemented contracts.

## Q004 — Cell-fault/HV-block calibration and false-positive strategy
Architecture and a conservative deterministic rule exist: ordinary heuristic risk or first SG imbalance does not veto corrective HV; automatic HV is denied only for strong cell-fault evidence, including explicit external confirmation or high-confidence multi-signal evidence with independent confirmation classes. Diagnostic inference itself cannot create a hard safety stop.

Still validate/calibrate against real traces and bench observations, especially:
- post-charge/rest total OCV when battery is known full and isolated;
- repeatable abnormal relaxation/self-discharge;
- persistent cell-level SG imbalance after corrective equalization/retest;
- abnormal thermal response;
- repeated recovery non-response;
- controlled dynamic-loop trend under unchanged connection;
- external conductance/load/CCA evidence when available.

Calibration must keep distinguishing “equalization may help” from “additional HV may be unsafe”. `battery_fault_calibration.py` / `tools/evaluate_battery_fault.py` now report unexpected and missed `BLOCK_AUTOMATIC_HV` independently so a single aggregate accuracy number cannot hide either failure class.

## Q005 — Controlled diagnostic-probe execution parameters
Principle, fail-closed executor and restart journal exist. A probe may only reduce/equal energy, samples median U/I, restores exact prior current transactionally, and forces Output OFF if restoration cannot be proven. `ΔV/ΔI` remains a two-wire dynamic-loop response, not battery Ri. A crash never resumes a probe mid-step.

Still define before automatic triggering:
- stages where automatic probe is allowed;
- step amplitude relative to current/C-rate;
- baseline/response windows;
- minimum telemetry freshness/sample cadence;
- thermal/headroom conditions;
- abort conditions;
- connection identity lifecycle;
- meaningful repeated-probe change given RD6018 resolution/noise.

## Q011 — Expert EFB 17.2–17.5 V workflow
17.5V is absolute controller/manual ceiling, not standard recipe. Before expert EFB HV becomes selectable define prerequisites/evidence, confirmation UX, current/time/thermal limits, exclusions, watchdog/readback requirements, audit label and authorization expiry. Per D051, any expert authorization must be revoked by process restart.

## Q013 — Active Bank-Fault hypothesis scoring/calibration
Hypothesis engine separates `cell_fault`, `self_discharge`, `sulfation`, `stratification`, `capacity_loss`, `thermal_abnormality`, and `charger_path`, with contradictory evidence and conservative automatic-HV veto boundary.

Deterministic calibration tooling is now implemented:
- JSONL labeled case loader;
- exact replay through current `assess_battery_fault()`;
- authority match accounting;
- separate `unexpected_hv_blocks` and `missed_hv_blocks` counters;
- per-hypothesis expected/actual level mismatches;
- machine-readable report CLI at `tools/evaluate_battery_fault.py`;
- no automatic score/threshold tuning.

What remains genuinely open is empirical calibration against real labeled cases. Do not change current 15/35/60/80 level boundaries or evidence weights merely to make synthetic examples look nicer. Required case classes and labeling rules are in `BANK_FAULT_CALIBRATION.md`.

SG prompt eligibility is deterministic (D053): only the exact physical battery with confirmed serviceable electrolyte access can be prompted, and only at diagnostic VERIFY+ for SG-relevant hypotheses or as a post-corrective retest of prior imbalance. Q013 still owns the real-data calibration that decides when evidence reaches VERIFY/PROBABLE/HIGH.

## Q014 — RD6018 dynamic-loop/relay-path calibration
Need on-device characterization of:
- `V_OUT` vs `V_BAT` offset/resolution under battery-mode relay load;
- repeatability of controlled `ΔI -> ΔV_BAT` response;
- effect of cable/clip reconnection;
- practical sample interval through current ESPHome/Modbus path;
- whether relay-path trend has enough signal above ADC quantization to retain as health metric.

## Q015 — Final main-merge compatibility plan
Before merging V2 to `main`, verify traceably:
- atomic AUTO start: `<12.0V -> PREP`, `>=12.0V -> MAIN`;
- Normal full automatic recovery/Mix behavior;
- Diagnostic no-automatic-HV behavior;
- Auto Mix direct entry;
- Ca/EFB three-attempt session recovery budget + 72h fallback;
- AGM four-attempt budget, staged Main and conservative 72h behavior;
- Mix 20/24/10 and sticky finish hold;
- SAFE_WAIT;
- Done/Storage Output ON;
- Manual native UI, quick-command migration, optional battery identity and interrupted re-authorization;
- Manual stop conditions;
- AUTO Manual-OFF as terminal asynchronous kill-condition only;
- Cooling;
- restart/restore including diagnostic action journal;
- link loss / edge lease / fast HV watchdog;
- RD readback/protection decode;
- Bank Fault/SG diagnostics including physical SG access gating and explicit correction metadata;
- Telegram dashboard/operator messages;
- exact ESPHome node compile/flash and physical RD6018 smoke/bench tests.

Intentional incompatibilities must be recorded in `V2_DECISION_LOG.md`, not discovered after deployment.

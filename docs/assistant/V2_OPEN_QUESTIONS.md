# V2 Open Questions

> Only unresolved strategy/product questions live here. Resolved behavior belongs in `V2_DECISION_LOG.md`.

Q001, Q002, Q003, Q006, Q007, Q008, Q009, Q010, Q011 and Q012 are intentionally retired: initial PREP handling, Manual identity/re-authorization, AUTO Manual-OFF semantics, post-heavy-recovery rest authority, intent semantics, 72h Main fallback, AGM recovery policy, diagnostic restart persistence, generic expert-EFB HV policy and SG access/correction/prompt policy now have accepted/implemented contracts.

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

The data path needed to calibrate this is now complete in software:
- `bench_capture.py` / `tools/capture_dynamic_loop.py` collect **read-only** actual HA-source observations with real Vbat/current timestamps, source skew, stable `connection_id`, configured current, Vout, battery temperature, CC/CV mode and RD/calibration identity when available;
- duplicate HA polls are discarded by source timestamp identity rather than converted into synthetic samples;
- missing source timestamps reject the sample rather than substituting local fetch time;
- `probe_characterization.py` / `tools/characterize_dynamic_loop.py` measure actual cadence, signal MAD/span, observed value steps, actual `ΔI/ΔV`, tail-deviation settling traces and descriptive Vout-Vbat behavior without choosing production thresholds;
- the capture tool has no actuator path: baseline/stepped/restored current changes remain explicit operator actions during characterization.

Detailed bench procedure and schema are in `DYNAMIC_LOOP_CALIBRATION.md`.

What remains open is now strictly **physical calibration from real captures**, not capture-tool design. Still define from those real traces, never from placeholder `ProbePlan` defaults:
- stages/modes where automatic probe is allowed;
- step amplitude relative to current/C-rate and measured noise;
- baseline/response/settle windows;
- minimum telemetry freshness/sample cadence;
- thermal/headroom conditions;
- abort conditions;
- connection identity lifecycle;
- meaningful repeated-probe change given RD6018 resolution/noise;
- Mix containment headroom above confirmed finish `ΔI` and the absolute measurement floor;
- safe current/OCP tightening sequence and reliable `CURRENT_CEILING_REACHED` classification before the implemented adaptive ratchet gains actuator authority.

Do not grant automatic diagnostic-probe or adaptive-current actuator authority merely because the software capture/analyzer/ratchet infrastructure exists.

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
The read-only capture + offline characterization/reporting path now exists; the remaining blocker is **actual RD6018/ESPHome/HA data from the physical installation**.

`tools/capture_dynamic_loop.py` can now record source-timestamped `baseline`, `stepped` and optional `restored` phases without changing RD6018 state itself. This removes the software-observability blocker but does not validate the measurement or authorize automatic probing.

Need on-device characterization of:
- `V_OUT` vs `V_BAT` offset/noise/observed quantization under battery-mode relay load;
- repeatability of controlled `ΔI -> ΔV_BAT` response;
- settling trajectory after the current reduction;
- effect of cable/clip reconnection using distinct `connection_id` values;
- actual sample cadence and source skew through the installed ESPHome/Modbus/HA path;
- stability across RD firmware/calibration identity;
- whether the dynamic-loop trend has enough signal above noise/quantization to retain as health evidence;
- the current-resolution/noise floor needed by adaptive Mix containment and the protected current/OCP tightening path.

`V_OUT - V_BAT` remains descriptive only. Q014 must not reinterpret it as cable/path resistance without independent RD6018 topology evidence.

Q014 closes only after real captures establish that the signal is repeatable and diagnostically useful. If not, dynamic-loop evidence and dependent automatic actuation should be removed/disabled rather than rescued by arbitrary thresholds.

## Q015 — Final main-merge compatibility plan
Before merging V2 to `main`, verify traceably:
- atomic AUTO start: `<12.0V -> PREP`, `>=12.0V -> MAIN`;
- Normal full automatic recovery/Mix behavior;
- Diagnostic no-automatic-HV behavior;
- Auto Mix direct entry;
- Ca/EFB three-attempt session recovery budget + 72h fallback;
- AGM four-attempt budget, staged Main and conservative 72h behavior;
- Mix 20/24/10 active-time authority plus sticky finish hold;
- `MIX_TIMEOUT` is terminal stop+diagnose with verified OFF, never SAFE_WAIT/Storage success;
- durable Mix active-time restart/Cooling/OFF semantics and fail-closed missing/corrupt state;
- SAFE_WAIT;
- Done/Storage Output ON only for normal completion;
- Manual native UI, quick-command migration, optional battery identity and interrupted re-authorization;
- Manual stop conditions;
- AUTO Manual-OFF as terminal asynchronous kill-condition only;
- Cooling;
- restart/restore including diagnostic action journal;
- 15min/5min link-loss edge lease on exact flashed ESPHome node;
- RD readback/protection decode;
- external-temperature disconnect/reconnect/source-timestamp characterization before Class-C numeric thresholds or a raw sentinel gain authority;
- Bank Fault/SG diagnostics including physical SG access gating and explicit correction metadata;
- EFB chemistry envelopes never exceed generic 16.5V; >16.5V requires Manual or a future explicit model-specific manufacturer-backed recipe;
- controlled-probe characterization against actual cadence/noise/settling before any automatic trigger policy is enabled;
- adaptive Mix current ratchet remains non-actuating until Q005/Q014 data establish headroom/floor/CV-CC/OCP sequencing, then receives a separate BENCH proof before enablement;
- Telegram dashboard/operator messages;
- exact ESPHome node compile/flash and physical RD6018 smoke/bench tests.

Intentional incompatibilities must be recorded in `V2_DECISION_LOG.md`, not discovered after deployment.

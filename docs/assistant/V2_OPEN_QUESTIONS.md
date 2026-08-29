# V2 Open Questions

> Only unresolved strategy/product questions live here. Resolved behavior belongs in `V2_DECISION_LOG.md`.

Q001, Q007, Q008 and Q009 are intentionally retired: initial PREP handling, intent semantics, 72 h Main fallback and AGM recovery policy are now accepted/implemented decisions.

## Q002 — Manual battery identity and interrupted-session re-authorization UX
Core Manual authority and input migration are implemented:
- operator V/I;
- derived, non-overridable OVP/OCP;
- absolute 17.5V / 12A envelope;
- arbitrary combinations of timer/V>=/V<=/V=/I>=/I<=/I=/delta stop conditions;
- no chemistry transitions;
- Cooling pause/resume;
- no silent Output re-enable after restart;
- native V2 Manual entry/help;
- old direct `V I` / `V I third-condition` commands are intercepted before the legacy handler and become managed Manual sessions;
- active Manual reconfiguration uses verified OFF -> fresh safe-enable rather than live unverified setpoint writes.

Still open:
- bind an optional saved battery identity for longitudinal history without granting chemistry authority;
- define the operator review/re-authorization UX for a persisted `INTERRUPTED` Manual request.

## Q003 — Legacy Manual-OFF interaction with automatic profiles
For explicit Manual, resolved: user conditions own normal completion; hard safety wins; chemistry rules do not run. The persistent legacy Manual-OFF overlay is also observed by the managed Manual runtime so Output cannot be OFF while Manual remains logically ACTIVE.

Remaining question applies only to automatic profiles that still use the legacy persistent `manual_off` engine: should arming a user stop condition suppress any automatic non-safety completion/escalation, or merely provide an additional earlier kill condition? Normalize this before removing the legacy side channel.

## Q004 — Cell-fault/HV-block calibration and false-positive strategy
Architecture and an initial deterministic rule are implemented: ordinary heuristic risk or first SG imbalance does not veto corrective HV; automatic HV is denied only for strong cell-fault evidence, including explicit external confirmation or high-confidence multi-signal evidence with independent confirmation classes. Diagnostic inference itself cannot create a hard safety stop.

Still validate/calibrate the thresholds against real stored traces and bench observations, especially combinations of:
- post-charge/rest total OCV while the battery is known full and isolated;
- repeatable abnormal relaxation/self-discharge;
- persistent cell-level SG imbalance after corrective equalization/retest;
- abnormal thermal response;
- repeated recovery non-response;
- controlled dynamic-loop response trend under unchanged connection;
- external conductance/load/CCA evidence when available.

The calibration must continue to distinguish “equalization may help” from “additional HV may be unsafe”.

## Q005 — Controlled diagnostic-probe execution parameters
Principle and fail-closed executor are implemented: a probe may only reduce/equal energy, samples median U/I, restores the exact prior current transactionally, and forces Output OFF if restoration cannot be proven. `ΔV/ΔI` remains a two-wire dynamic-loop response, not battery Ri.

Still define before automatic triggering:
- stages where automatic probe is allowed;
- step amplitude relative to current/C-rate;
- baseline and response windows;
- minimum telemetry freshness/sample cadence;
- thermal/headroom conditions;
- abort conditions;
- connection identity lifecycle;
- how much change across repeated probes is meaningful given RD6018 resolution/noise.

## Q006 — 24–48 h rest after heavy recovery
Decide whether this is:
- recommendation only;
- dashboard/diagnostic window;
- scheduled longitudinal measurement window;
- or hard lockout on another aggressive recovery.

Do not add a mandatory lockout implicitly.

## Q010 — Persistence matrix for diagnostic sub-states
Manual restart behavior is resolved: active Manual restores `INTERRUPTED`, never auto-ON. Exact-reach compatibility conditions are persisted with the Manual request.

Still define persistence/restore for:
- diagnostic probe in progress (likely abort + mark invalid rather than resume mid-probe);
- pending operator confirmation;
- HV block / fault-verification state;
- expert-HV authorization;
- optional heavy-charge rest state.

For each: persist? expire? restore automatically? require fresh telemetry/operator confirmation?

## Q011 — Expert EFB 17.2–17.5 V workflow
17.5V exists as the absolute controller/manual ceiling, not a standard recipe. Before expert EFB HV becomes selectable define prerequisites/evidence, confirmation UX, current/time/thermal limits, exclusions, watchdog/readback requirements and audit label.

## Q012 — Specific-gravity correction/prompt policy
Foundation and Telegram entry are implemented:
- saved physical battery selection;
- six positional cell slots;
- missing cell explicitly `None`;
- raw SG retained;
- timestamp, measurement temperature, context/source/notes stored;
- full spread >=0.030 means imbalance/stratification evidence, not confirmed failed cell and not an automatic equalization veto.

Still define:
- manufacturer/hydrometer-specific temperature correction policy;
- which charge/diagnostic points should proactively ask the operator for SG;
- how applicability metadata should distinguish flooded batteries from EFB designs with inaccessible cells.

## Q013 — Active Bank-Fault hypothesis scoring/calibration
The hypothesis engine separates `cell_fault`, `self_discharge`, `sulfation`, `stratification`, `capacity_loss`, `thermal_abnormality`, and `charger_path`, with contradictory evidence and a conservative automatic-HV veto boundary. Thresholds/confidence still need validation against stored traces rather than cosmetic tuning.

## Q014 — RD6018 dynamic-loop/relay-path calibration
Need on-device characterization of:
- `V_OUT` vs `V_BAT` offset/resolution under battery-mode relay load;
- repeatability of controlled `ΔI -> ΔV_BAT` response;
- effect of cable/clip reconnection;
- practical sample interval via current ESPHome/Modbus path;
- whether relay-path trend has enough signal above ADC quantization to keep as a health metric.

## Q015 — Final main-merge compatibility plan
Before merging V2 to `main`, verify traceably:
- atomic auto start: `<12.0V -> PREP`, `>=12.0V -> MAIN`;
- Normal full automatic recovery/Mix behavior;
- Diagnostic no-automatic-HV behavior;
- Ca/EFB three-attempt session recovery budget and 72h fallback;
- AGM four-attempt session recovery budget, staged Main and conservative 72h behavior;
- Mix 20/24/10 and sticky finish hold;
- SAFE_WAIT;
- Done/Storage Output ON;
- Manual native UI, direct-command migration and interrupted-session UX;
- Manual stop conditions and persistent Manual-OFF interaction;
- Cooling;
- restart/restore;
- link loss / edge lease / fast HV watchdog;
- RD readback/protection decode;
- Bank Fault/SG diagnostics;
- Telegram dashboard/operator messages.

Intentional incompatibilities must be recorded in `V2_DECISION_LOG.md`, not discovered after deployment.

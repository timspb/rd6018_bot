# V2 Open Questions

> Only unresolved strategy/product questions live here. Resolved behavior belongs in `V2_DECISION_LOG.md`.

## Q001 — Initial Vbat >=12 V: atomically skip PREP?
Known: below ~12V current must remain small. V1 can be logically PREP while physically applying Main target for an initially >=12V battery. Decide exact boundary/hysteresis and restore behavior for:

```text
Vbat < threshold  -> PREP
Vbat >= threshold -> MAIN directly + PREP-skipped audit event
```

## Q002 — Native V2 Manual UI and command migration
Manual backend/authority is now defined and implemented:
- operator V/I;
- derived, non-overridable OVP/OCP;
- absolute 17.5V / 12A envelope;
- operator stop conditions own normal completion;
- no chemistry transitions;
- Cooling pause/resume;
- no silent Output re-enable after restart.

Still open:
- replace the legacy five-step Custom dialog with a native V2 Manual UI;
- expose the full 17.5V range in UI (legacy dialog still presents 17.0V max);
- expose arbitrary combinations of timer/V>=/V<=/I>=/I<=/delta cleanly;
- bind an optional saved battery identity for history without granting chemistry authority;
- migrate old direct `V I` / `V I third-condition` text commands into the managed Manual session instead of unmanaged setpoint writes;
- define operator re-authorization UX for an `INTERRUPTED` persisted Manual request.

## Q003 — Legacy Manual-OFF interaction with automatic profiles
For explicit Manual, resolved: user conditions own normal completion; hard safety wins; chemistry rules do not run.

Remaining question applies only to automatic profiles that still use the legacy persistent `manual_off` engine: should arming a user stop condition suppress any automatic non-safety completion/escalation, or merely provide an additional earlier kill condition? Normalize this before removing the legacy side channel.

## Q004 — Exact cell-fault/HV-block confirmation rule
Architecture is decided: hypothesis-specific diagnostics may block further automatic HV when a cell fault is strongly confirmed. A generic score or one sample cannot.

Need deterministic multi-signal criteria and false-positive strategy. Candidate evidence classes:
- post-charge/rest total OCV inconsistent with six healthy cells;
- repeatable abnormal relaxation/self-discharge while battery is known isolated;
- cell-level SG imbalance plus supporting total-voltage/trajectory evidence;
- abnormal thermal response;
- repeated recovery non-response;
- controlled dynamic-loop response trend under unchanged connection;
- external conductance/load/CCA evidence when available.

This must distinguish “equalization may help” (e.g. flooded SG imbalance/stratification) from “additional HV may be unsafe” (credible failed/shorted cell).

## Q005 — Controlled diagnostic-probe execution parameters
Principle is accepted: diagnostic probes may only reduce/equal energy, restore the exact prior setpoints transactionally, and `ΔV/ΔI` is a two-wire dynamic-loop response, not battery Ri.

Still define:
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

## Q007 — User-facing meaning of Normal / Recovery / Conditioning
Current V2 model makes Normal/Diagnostic non-HV and Recovery/Conditioning HV-capable by evidence, while legacy automatic Ca/EFB historically included Mix in its normal chain. Before merge to main, explicitly confirm naming/workflow compatibility so operator expectations are not changed by terminology alone.

## Q008 — 72 h Main fallback under intent model
V1 72h Ca/EFB fallback is accepted behavior. Decide V2 interaction:
- only Recovery/Conditioning -> Mix;
- legacy-compatible auto regardless of intent naming;
- Normal -> diagnose/finish rather than Mix;
- operator confirmation at timeout.

This is separate from stuck-current recovery attempts.

## Q009 — Final AGM recovery-attempt policy
AGM conservative asymmetry is accepted. Still decide:
- max intermediate recovery attempts;
- whether budget is session-wide exactly like Ca/EFB;
- behavior after budget exhausted;
- conditions for final Mix after 15.0V Main;
- whether REHYDRATED AGM modifies transitions or only envelope/diagnostics.

## Q010 — Persistence matrix for diagnostic sub-states
Manual restart behavior is now resolved: active Manual restores `INTERRUPTED`, never auto-ON.

Still define persistence/restore for:
- diagnostic probe in progress (likely abort + mark invalid rather than resume mid-probe);
- pending operator confirmation;
- HV block / fault-verification state;
- expert-HV authorization;
- optional heavy-charge rest state.

For each: persist? expire? restore automatically? require fresh telemetry/operator confirmation?

## Q011 — Expert EFB 17.2–17.5 V workflow
17.5V exists as the absolute controller/manual ceiling, not a standard recipe. Before expert EFB HV becomes selectable define prerequisites/evidence, confirmation UX, current/time/thermal limits, exclusions, watchdog/readback requirements and audit label.

## Q012 — Specific-gravity workflow/UI and correction policy
Foundation implemented:
- six positional cell slots;
- missing cell explicitly `None`;
- raw SG retained;
- timestamp, measurement temperature, context/source/notes stored;
- full spread >=0.030 currently means `VERIFY`, not confirmed fault.

Still define:
- Telegram entry/edit UX;
- flooded/EFB applicability metadata;
- manufacturer/hydrometer-specific temperature correction policy;
- which charge/diagnostic points should ask the operator for SG;
- how SG evidence feeds Q004 without confusing stratification/equalization need with short-cell risk.

## Q013 — Active Bank-Fault hypothesis scoring/calibration
The old single V1 score must be decomposed. Need scoring/likelihood calibration for `cell_fault`, `self_discharge`, `sulfation`, `stratification`, `capacity_loss`, `thermal_abnormality`, `charger_path`, including confidence and contradictory evidence. Thresholds must be validated against stored traces rather than chosen cosmetically.

## Q014 — RD6018 dynamic-loop/relay-path calibration
Need on-device characterization of:
- `V_OUT` vs `V_BAT` offset/resolution under battery-mode relay load;
- repeatability of controlled `ΔI -> ΔV_BAT` response;
- effect of cable/clip reconnection;
- practical sample interval via current ESPHome/Modbus path;
- whether relay-path trend has enough signal above ADC quantization to keep as a health metric.

## Q015 — Final main-merge compatibility plan
Before merging V2 to `main`, verify traceably:
- auto start and PREP boundary;
- Ca/EFB recovery cycles and 72h fallback;
- AGM staged Main;
- Mix 20/24/10 and sticky finish hold;
- SAFE_WAIT;
- Done/Storage Output ON;
- Manual native UI + direct-command migration;
- Manual stop conditions;
- Cooling;
- restart/restore;
- link loss / edge lease / fast HV watchdog;
- RD readback/protection decode;
- Bank Fault/SG diagnostics;
- Telegram dashboard/operator messages.

Intentional incompatibilities must be recorded in `V2_DECISION_LOG.md`, not discovered after deployment.

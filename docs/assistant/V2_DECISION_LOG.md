# V2 Decision Log

> Durable source of truth for decisions made after the V1 behavioral audit.
> Do not infer strategy from implementation details alone. If behavior changes, update this file with code/tests.

Status: **ACCEPTED** = target behavior; **IMPLEMENTED** = present on this branch; **OPEN** = unresolved; **REJECTED** = explicitly not intended.

## D001 — V1 is a multi-layer behavioral system
**ACCEPTED.** V2 must preserve/review operator UI, chemistry FSM, actuator sequencing, HA/RD readback, watchdogs, Manual/unmanaged paths, persistence/restore, diagnostics/logging. Reference: `V1_BEHAVIORAL_AUDIT.md`.

## D002 — Vin is PSU-health telemetry, not Pb FSM authority
**ACCEPTED / IMPLEMENTED.** `input_voltage` may diagnose the upstream PSU, but it does not grant/deny battery-stage authority and low/missing Vin is not itself a Pb shutdown condition.

## D003 — Absolute V2 working-voltage ceiling is 17.5 V
**ACCEPTED / IMPLEMENTED.** Anything above 17.5 V is rejected before hardware enable. Chemistry/intent recipes may impose lower limits.

## D004 — BAT_MODE is observation, not permission
**ACCEPTED / IMPLEMENTED.** RD6018 owns its battery-relay hardware logic. V2 observes `BAT_MODE`; it does not require it as a software start permission.

## D005 — commanded, configured/readback and measured values are distinct
**ACCEPTED / IMPLEMENTED.** HA HTTP success is insufficient. Managed output follows program -> configured-value readback -> verify -> Output ON -> post-enable physical verification.

## D006 — raw RD telemetry semantics must be explicit
**ACCEPTED / IMPLEMENTED FOUNDATION.** Explicit CV/CC mode, raw protection status (`Normal/OVP/OCP/OPP`), corrected Pout/temp decoding, model/serial/firmware, calibration/system state and source freshness are first-class telemetry. Legacy entities are migration fallback only.

## D007 — initial battery voltage chooses PREP or MAIN before first Output ON
**ACCEPTED / IMPLEMENTED.** `Vbat < 12.0 V` -> PREP with ~0.01C. `Vbat >= 12.0 V` -> MAIN directly, with `PREP_SKIPPED` audit before first safe enable. Restore uses persisted stage/target and does not rerun this shortcut.

## D008 — Main normal-tail and stuck-plateau are separate evidence
**ACCEPTED.** Stable low-current tail is not lack of progress. Slowly declining current is not a flat plateau.

## D009 — Ca/EFB recovery attempts are session-wide
**ACCEPTED / IMPLEMENTED.** Three attempts belong to the whole Main/recovery portion of one charge session. Progress does not reset the counter; only a new session does.

## D010 — after Ca/EFB recovery budget, next confirmed plateau -> final Mix
**ACCEPTED / IMPLEMENTED.** Safety, telemetry, thermal and diagnostic HV veto still outrank this transition.

## D011 — AGM is intentionally conservative/asymmetric
**ACCEPTED / IMPLEMENTED.** AGM uses four recovery attempts/session. After attempt #4, another plateau does not force Mix; remain Main and wait for normal low-current tail or conservative 72h fallback.

## D012 — 72h Main is strategy fallback, not generic hard safety
**ACCEPTED / IMPLEMENTED.** Ca/EFB Normal/Recovery/Conditioning -> Mix at 72h. AGM -> Mix only when already CV with `I <= 0.20 A`, otherwise stop+diagnose. Diagnostic -> stop+diagnose. Rollback legacy timeout behavior may remain only in legacy scaffold.

## D013 — SAFE_WAIT 2h is a maximum relaxation wait
**ACCEPTED.** Reach threshold earlier -> continue immediately; otherwise continue after max ~2h. Slow relaxation is diagnostic evidence, not automatically a fault.

## D014 — Mix delta is mode-specific
**ACCEPTED.** CV uses `Imin -> confirmed ΔI rise`; CC uses `Vmax -> confirmed ΔV fall`. Controlled variable is not independent finish evidence.

## D015 — Mix needs spaced confirmations
**ACCEPTED.** Approximately 3 confirmations, ~60s spacing, after ~120s post-setpoint blanking.

## D016 — confirmed Mix delta starts sticky 2h finish hold
**ACCEPTED / IMPLEMENTED.** Later small threshold recrossing does not erase an already-established event. Hard safety still wins.

## D017 — Mix fallback maxima are Ca 20h / EFB 24h / AGM 10h
**ACCEPTED / IMPLEMENTED.** These are fallback observation maxima, not target durations.

## D018 — Done means managed Storage/float remains ON
**ACCEPTED.** Normal completion: `SAFE_WAIT -> Done/Storage -> ~13.8 V / 1 A -> Output ON`. Fault/hard-stop has separate OFF semantics.

## D019 — Cooling is a pause, not a chemistry stage
**ACCEPTED / IMPLEMENTED.** Output OFF; exact source target preserved; active clocks frozen; recovery budget/AGM step/extrema/confirmed delta preserved; stuck plateau and incomplete delta continuity invalidated; state is persistable/restorable.

## D020 — Manual is a first-class supported mode
**ACCEPTED / IMPLEMENTED.** Manual owns output independently from Pb chemistry FSM; it is not `Idle + Output ON` and not legacy Custom chemistry authority.

## D021 — Manual working inputs are operator-defined; protections are not
**ACCEPTED / IMPLEMENTED.** Operator supplies V/I and optional stop rules. OVP/OCP are always derived and cannot be weakened. Envelope: `0 < V <= 17.5 V`, `0 < I <= 12 A`.

## D022 — Manual completion belongs to operator; hard safety outranks everything
**ACCEPTED / IMPLEMENTED.** Timer/V/I/reach/delta conditions may end Manual. Pb chemistry transitions do not run. Thermal/electrical/readback/watchdog safety is non-bypassable.

## D023 — Manual Cooling preserves exact program
**ACCEPTED / IMPLEMENTED.** Battery T >=40C -> OFF/Cooling; <=35C -> safe restore same V/I; >=45C -> terminal stop. Active-time timer pauses and continuity-dependent evidence restarts fresh.

## D024 — Manual never silently re-energizes after process restart
**ACCEPTED / IMPLEMENTED.** Persisted ARMING/ACTIVE/COOLING restores as `INTERRUPTED`; Output ON requires fresh operator authorization and a fresh safe-enable transaction.

## D025 — Manual stop conditions are operator kill conditions
**ACCEPTED / IMPLEMENTED.** `V>=`, `V<=`, `V=reach`, `I>=`, `I<=`, `I=reach`, timer/delta are not chemistry evidence. AUTO interaction is separately defined by D050.

## D026 — bank/cell fault inference must be hypothesis-specific
**ACCEPTED / FOUNDATION IMPLEMENTED.** Separate cell fault, self-discharge, sulfation, stratification, capacity loss, thermal abnormality and charger/path hypotheses. V1 one-score risk is evidence, never proof.

## D027 — Bank Fault becomes an active diagnostic contour
**ACCEPTED.** Bounded experiments may confirm/refute hypotheses only in a safer/equal-energy direction, must restore prior settings transactionally, and must never invent extra HV merely to test a battery.

## D028 — confirmed cell-fault evidence may block further automatic HV
**ACCEPTED / IMPLEMENTED CONSERVATIVELY.** A planned Recovery/Mix may be denied only by strong independent cell-fault evidence. One heuristic score, one U/I sample or first SG imbalance is insufficient. Diagnostic inference itself never creates `HARD_STOP`.

## D029 — per-cell specific gravity is first-class external evidence
**ACCEPTED / IMPLEMENTED FOUNDATION + UI.** Store six positional cells, raw SG, temperature, timestamp, context/source/notes. Missing cells stay explicit `None`. First complete spread >=0.030 means imbalance/stratification evidence, not short-cell proof and not automatic equalization veto.

## D030 — RD6018 displayed V/I resistance is not battery internal resistance
**ACCEPTED.** Ordinary `V/I` adds no independent battery-Ri evidence during charging.

## D031 — controlled ΔV/ΔI is a two-wire dynamic-loop response
**ACCEPTED / IMPLEMENTED FOUNDATION.** Black+green use the same charging wires; response includes battery+cables+contacts+internal path/polarization. Store as `dynamic_loop`, never battery Ri. Longitudinal comparison requires unchanged `connection_id`.

## D032 — RD identity/calibration/system state are diagnostic context
**ACCEPTED / IMPLEMENTED FOUNDATION.** Model/serial/firmware and read-only calibration fingerprint invalidate stale hardware baselines when changed. Automatic energizing settings such as Boot Power/Take Out are incompatible with managed charging when exposed.

## D033 — AI remains advisory only
**ACCEPTED.** AI may explain evidence/hypotheses but cannot choose setpoints, authorize HV or override deterministic safety.

## D034 — higher-energy state means shorter blind-operation tolerance
**ACCEPTED.** Preserve fast-HV-watchdog principle; edge lease/readback may harden it but never weaken it.

## D035 — chemistry strategy and actuator safety are separate layers
**ACCEPTED.** A chemically allowed transition still requires fresh telemetry, thermal checks, recipe envelope, OVP/OCP, V/I readback, Output verification and watchdog coverage.

## D036 — universal `>~1%C plateau => HV veto` is rejected
**REJECTED / REMOVED.** Current magnitude may contribute to diagnostics but is not a one-number universal HV veto.

## D037 — 24–48h post-heavy-recovery rest is diagnostic window, not lockout
**ACCEPTED.** V2 may recommend rest and use ~1h/6h/12h/24h/48h checkpoints for OCV/Vbat, T, SG, recovery response and `battery_isolated`. Elapsed rest time alone never blocks Normal, Recovery, Conditioning, Manual or Auto Mix. Any HV denial must come from real safety/diagnostic evidence.

## D038 — every production Manual text entry converges on one managed authority
**ACCEPTED / IMPLEMENTED.** Native Manual and historic quick `V I` / `V I third-condition` become `ManualSession` operations; raw unmanaged writes are not production authority.

## D039 — active Manual reconfiguration is transactional
**ACCEPTED / IMPLEMENTED.** Verified OFF -> retire previous runner -> fresh safe-enable/readback with new request.

## D040 — historic `V I third` reach semantics are preserved
**ACCEPTED / IMPLEMENTED.** `15V` or `1.0A` means reach/cross target, not contradictory simultaneous inequalities.

## D041 — controlled current probe exists but automatic trigger policy is not guessed
**ACCEPTED / IMPLEMENTED EXECUTOR.** Probe only lowers current, collects median U/I, restores exact prior configured current, and forces Output OFF if restoration/readback cannot be proven. Automatic trigger parameters remain Q005/Q014.

## D042 — structured dialogs outrank global numeric Manual parser
**ACCEPTED / IMPLEMENTED.** Explicit pending SG/other structured input owns the next message; numeric payload is not automatically Manual.

## D043 — Normal preserves V1-compatible full automatic chain
**ACCEPTED / IMPLEMENTED.** Normal may use bounded intermediate recovery and final Mix according to evidence/budget/timeout rules. It is not a no-HV profile.

## D044 — Diagnostic is explicit no-automatic-HV intent
**ACCEPTED / IMPLEMENTED.** Diagnostic observes/concludes/stops without creating new Recovery/Mix.

## D045 — Recovery/Conditioning describe operator purpose, not bypass permission
**ACCEPTED / IMPLEMENTED FOUNDATION.** They remain inside deterministic evidence, recipe and safety authority. Expert EFB 17.2–17.5 is separate Q011.

## D046 — AGM recovery budget is four/session and exhaustion does not force Mix
**ACCEPTED / IMPLEMENTED.** Fifth confirmed plateau remains Main; normal tail or conservative 72h rule owns subsequent transition.

## D047 — diagnostic HV veto is applied to chosen transition
**ACCEPTED / IMPLEMENTED.** Strategy first decides action; then `BLOCK_AUTOMATIC_HV` may veto a planned `ENTER_DESULFATION`/`ENTER_MIX`, including Normal and timeout-generated Mix.

## D048 — production presentation must use production semantics
**ACCEPTED / IMPLEMENTED.** UI/status uses Normal full-auto, Diagnostic no-auto-HV and Mix fallback 20/24/10; rollback constants must not leak into operator contract.

## D049 — Auto Mix is first-class direct-entry automatic program
**ACCEPTED / IMPLEMENTED.** Session starts directly in `STAGE_MIX`; PREP/Main/intermediate recovery are never entered. `Vbat <12.0V` rejects start. Standard targets: Ca/EFB 16.5V, AGM 16.3V, ~0.03C; standard Delta/sticky2h/fallback/SAFE_WAIT/Storage and all safety/readback/diagnostic HV vetoes apply. Expert EFB HV is not implicitly authorized.

## D050 — AUTO Manual-OFF is asynchronous terminal kill-condition only
**ACCEPTED / IMPLEMENTED.** Merely arming persistent OFF does not suppress/alter PREP/Main/Recovery/Mix/72h/normal completion. If condition fires: terminal Output OFF + session stop + condition clear; do not enter Storage afterwards. Production AUTO strips legacy `manual_off_active=True` from chemistry tick while independent evaluator remains until legacy side-channel removal.

## D051 — diagnostic persistence stores evidence and action lifecycle, never resumes authority blindly
**ACCEPTED / IMPLEMENTED FOUNDATION.** Durable diagnostic evidence (SG, completed dynamic-loop measurements, recovery history) may survive restart. Derived `ALLOW/VERIFY/BLOCK_AUTOMATIC_HV` is not persisted as authority; it is recomputed from available evidence. A durable action journal records nonterminal diagnostic work with restart rules: in-flight probe -> `ABORTED_RESTART` and defensive Output OFF; pending operator/fault verification -> `EXPIRED_RESTART`; expert-HV authorization -> `REVOKED_RESTART`; rest-observation may survive until its expiry because it has no actuator authority. No diagnostic action resumes mid-step after crash.

## D052 — Manual battery identity is optional metadata; interrupted Manual requires explicit fresh re-authorization
**ACCEPTED / IMPLEMENTED.** Operator may bind Manual to a saved physical `battery_id` solely for longitudinal history/diagnostics. Saved chemistry/capacity never changes Manual V/I, OVP/OCP or permissions. After process restart, the preserved request is reviewable as `INTERRUPTED`; operator must explicitly re-authorize. Re-authorization runs a complete fresh telemetry/safety/readback/Output transaction and restarts active-time accounting. A missing/deleted saved battery binding prevents reusing that bound request until operator chooses an actual battery or an unbound new Manual request.

## Current implementation checkpoints

- `1bd67cb...`: corrected RD telemetry, freshness/readback, 17.5V absolute envelope.
- `abfcbda...`: Cooling pause semantics, Ca/EFB session recovery budget, Mix 20/24/10h.
- `0dbf744...` + `690f82d...`: hypothesis/SG/dynamic-loop evidence and durable storage.
- `085eb08...`: Vin diagnostics-only semantics.
- `a693090...` + `54fd424...`: unified Manual authority and transactional reconfiguration.
- `bb3ff05...` + `b68f943...`: structured SG precedence over numeric Manual parser.
- `60d1bc96...`: full AUTO/72h/AGM strategy + atomic PREP skip.
- `97a16efd...`: Auto Mix direct-entry program.
- `8a7bec13...`: AUTO Manual-OFF isolated from chemistry authority.
- `dd7e3af...` + `c3a4957...` + `3ebf6a5...`: diagnostic action journal, startup recovery and tests.
- `0bcec05...` + `6981f1b...` + `00d877e...`: Manual optional physical-battery identity and interrupted-request reauthorization UX/tests.

## Maintenance rule
Whenever behavior changes: update/add a numbered decision, update `CHARGE_STRATEGY.md` when production strategy changes, remove resolved items from `V2_OPEN_QUESTIONS.md`, add deterministic tests, and keep code/docs in the same change where practical.

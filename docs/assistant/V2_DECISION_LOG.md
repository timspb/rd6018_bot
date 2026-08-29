# V2 Decision Log

> Durable source of truth for decisions made after the V1 behavioral audit.
> Do not infer strategy from implementation details alone. If behavior changes, update this file with code/tests.

Status: **ACCEPTED** = target behavior; **IMPLEMENTED** = present on this branch; **OPEN** = unresolved; **REJECTED** = explicitly not intended.

## D001 — V1 is a multi-layer behavioral system
**ACCEPTED.** V2 must preserve/review operator UI, chemistry FSM, actuator sequencing, HA/RD readback, watchdogs, Manual/unmanaged paths, persistence/restore, diagnostics/logging. Reference: `V1_BEHAVIORAL_AUDIT.md`.

## D002 — Vin is PSU-health telemetry, not Pb FSM authority
**ACCEPTED / IMPLEMENTED.** `input_voltage` may be logged and used to diagnose the upstream PSU, but it does not grant/deny battery-stage authority and low/missing Vin is not itself a battery shutdown condition in production V2.

## D003 — Absolute V2 working-voltage ceiling is 17.5 V
**ACCEPTED / IMPLEMENTED.** `17.5 V` is accepted; anything above is rejected before hardware enable. Chemistry/intent recipes may impose lower limits. This is an outer envelope, not a default recovery target.

## D004 — BAT_MODE is observation, not permission
**ACCEPTED / IMPLEMENTED.** RD6018 decides whether its battery relay can close. V2 observes `BAT_MODE`; it does not require it as a software start permission.

## D005 — commanded, configured and measured values are distinct
**ACCEPTED / IMPLEMENTED FOUNDATION.** V2 distinguishes requested V/I/OVP/OCP, RD configured/readback values, and measured physical U/I. HA HTTP success alone is insufficient. Program -> readback -> verify -> Output ON -> verify again.

## D006 — raw RD telemetry semantics must be explicit
**ACCEPTED / IMPLEMENTED FOUNDATION.** Explicit CV/CC mode, raw protection status (`Normal/OVP/OCP/OPP`), corrected Pout/temp decode, model/serial/firmware, calibration/system state and HA source freshness are first-class telemetry. Legacy entities are migration fallbacks only.

## D007 — initial battery voltage chooses PREP or MAIN before first Output ON
**ACCEPTED / IMPLEMENTED.** At auto start, `Vbat < 12.0 V` uses PREP with the small ~0.01C current. `Vbat >= 12.0 V` atomically starts MAIN and records a PREP-skipped audit event before the first safe Output enable. Restore uses the persisted stage/target and does not rerun this initial shortcut.

## D008 — Main normal-tail and stuck-plateau are separate evidence
**ACCEPTED.** A successful stable tail is not the same event as lack of progress. Slowly declining current is not a flat plateau.

## D009 — Ca/EFB recovery attempts are session-wide
**ACCEPTED / IMPLEMENTED.** Three bounded recovery attempts belong to the whole Main/recovery session. Progress does not reset the counter; only a new charge session does.

## D010 — after Ca/EFB recovery budget, next confirmed stuck plateau -> final Mix
**ACCEPTED / IMPLEMENTED.** Safety/thermal/telemetry/diagnostic HV vetoes still outrank this transition.

## D011 — AGM is intentionally conservative/asymmetric
**ACCEPTED / IMPLEMENTED.** AGM uses four intermediate recovery attempts per charge session. Progress does not reset the count. After the fourth attempt, another stuck plateau does **not** force Mix: remain in Main and wait for the normal low-current tail or the conservative 72 h fallback. REHYDRATED AGM is context/diagnostic evidence, not a transition override.

## D012 — 72 h Main is a strategy fallback, not generic hard safety
**ACCEPTED / IMPLEMENTED IN PRODUCTION V2.** Ca/EFB at 72 h -> final Mix for HV-capable auto intents even without a fixed plateau. AGM at 72 h -> Mix only if already CV with `I <= 0.20 A`; otherwise stop/diagnose. Diagnostic intent stops/diagnoses rather than creating HV. The legacy scaffold retains its historical hard-timeout behavior for rollback reproducibility, but production V2 masks it during authoritative Main and applies this strategy explicitly.

## D013 — SAFE_WAIT 2 h is a maximum relaxation wait
**ACCEPTED.** Reach threshold earlier -> continue immediately. Otherwise continue after max 2h. Slow relaxation is diagnostic evidence, not automatically a fault.

## D014 — Mix delta is mode-specific
**ACCEPTED.** CV: `Imin -> confirmed ΔI rise`. CC: `Vmax -> confirmed ΔV fall`. Controlled variable is never treated as independent finish evidence.

## D015 — Mix needs spaced confirmations
**ACCEPTED.** Approximately 3 confirmations, ~60s spacing, with ~120s post-setpoint blanking.

## D016 — confirmed Mix delta starts sticky 2 h finish hold
**ACCEPTED / IMPLEMENTED.** Small later threshold recrossing does not erase the established event. Hard safety still wins.

## D017 — Mix fallback maxima are Ca 20 h / EFB 24 h / AGM 10 h
**ACCEPTED / IMPLEMENTED IN PRODUCTION V2.** These are fallback observation maxima, not normal target durations. An already-started valid 2h finish hold owns normal completion. Historical legacy constants may remain different only in rollback/scaffold code.

## D018 — Done means managed Storage/float remains ON
**ACCEPTED.** Normal completion: `SAFE_WAIT -> Done/Storage -> ~13.8 V / 1 A -> Output ON`. Fault/hard-stop must be represented separately.

## D019 — Cooling is a pause, not a chemistry stage
**ACCEPTED / IMPLEMENTED.** Output OFF; exact source target preserved; active clocks frozen; recovery budget/AGM step/extrema/confirmed delta preserved; stuck plateau and incomplete delta continuity invalidated; sticky finish hold timer paused; state persisted/restorable.

## D020 — Manual is a first-class supported mode
**ACCEPTED / IMPLEMENTED.** The production Manual runtime owns Manual output independently from the Pb chemistry FSM. Manual is not `Idle + Output ON` and is not legacy Custom chemistry authority.

## D021 — Manual working inputs are operator-defined; protections are not
**ACCEPTED / IMPLEMENTED.** Operator may define V/I and stop conditions. OVP/OCP are always derived from V/I and cannot be weakened manually. Production Manual UI/text authority exposes the full 17.5 V / 12 A envelope.

## D022 — Manual completion belongs to the operator, safety outranks everything
**ACCEPTED / IMPLEMENTED.** Automatic Pb transitions do not run in Manual. Operator stop conditions (timer, V/I thresholds, exact reach, optional mode-aware delta) own normal Manual completion. Hard thermal/electrical/readback/watchdog safety is non-bypassable.

## D023 — Manual Cooling preserves the exact manual program
**ACCEPTED / IMPLEMENTED.** At battery T >=40C Manual goes OFF/COOLING; active timer pauses; at <=35C the exact same V/I and freshly derived protections are safely re-applied; continuity-dependent delta/reach sampling proof resets. >=45C is terminal stop.

## D024 — Manual does not silently re-energize after process restart
**ACCEPTED SAFETY INVARIANT / IMPLEMENTED.** Persisted active/arming/cooling Manual state restores as `INTERRUPTED`; Output ON requires fresh operator re-authorization and normal safe-enable checks.

## D025 — Manual OFF / manual stop conditions are operator kill conditions
**ACCEPTED / IMPLEMENTED FOR MANUAL.** V>=, V<=, V=/reach, I>=, I<=, I=/reach, timer and equivalent Manual stop conditions are not chemistry evidence. Persistent legacy Manual-OFF is observed by managed Manual so Output cannot be OFF while Manual remains logically ACTIVE. Automatic-profile interaction remains Q003.

## D026 — bank/cell fault inference must be hypothesis-specific
**ACCEPTED / FOUNDATION IMPLEMENTED.** Replace one generic “bad battery” score with hypotheses such as cell fault, self-discharge, sulfation, stratification, capacity loss, thermal abnormality and charger/path fault. V1 heuristic score remains evidence, never proof.

## D027 — Bank Fault becomes an active diagnostic contour
**ACCEPTED.** Diagnostics may request/perform bounded experiments to confirm/refute hypotheses. They may alter charge only in a safer/equal-energy direction, must restore prior setpoints transactionally, and must never invent extra HV merely to “test” a battery.

## D028 — confirmed cell-fault evidence may block further automatic HV
**ACCEPTED / IMPLEMENTED CONSERVATIVELY.** A planned automatic Recovery/Mix escalation — including one from Normal or a 72 h fallback — may be denied only by strong cell-fault evidence. One heuristic score, one U/I sample or first SG imbalance cannot veto corrective equalization. Diagnostic inference cannot itself create `HARD_STOP`.

## D029 — per-cell specific gravity is first-class external evidence
**ACCEPTED / IMPLEMENTED FOUNDATION + UI.** For accessible flooded cells, store all six positions, raw SG, measurement temperature, timestamp, context, source and notes. Missing/inaccessible cells remain explicit `None`. A first full-cell spread >=0.030 is imbalance/stratification evidence, not “shorted cell” and not an automatic equalization veto.

## D030 — RD6018 displayed V/I resistance is not battery internal resistance
**ACCEPTED.** Ordinary `V/I` adds no independent battery-Ri evidence during charging and must not be labelled battery resistance.

## D031 — controlled ΔV/ΔI is a two-wire dynamic-loop response
**ACCEPTED / IMPLEMENTED FOUNDATION.** With black+green charging on the same two wires, a current-step response contains battery + cables + contacts + internal path/polarization. Store it as `dynamic_loop`, not laboratory battery Ri. Direct longitudinal comparison requires an explicit unchanged `connection_id`.

## D032 — RD identity/calibration/system state are diagnostic context
**ACCEPTED / IMPLEMENTED FOUNDATION.** Model/serial/firmware and read-only calibration fingerprint help invalidate stale baselines after hardware/firmware/calibration changes. `Boot Power`/`Take Out` automatic energizing is incompatible with managed charging when exposed.

## D033 — AI remains advisory only
**ACCEPTED.** AI may explain evidence/hypotheses; it cannot choose or execute setpoints or override deterministic authority.

## D034 — higher-energy state means shorter blind-operation tolerance
**ACCEPTED.** Preserve the V1 fast-HV-watchdog principle. Edge safety lease/readback hardening may improve implementation, never weaken it.

## D035 — chemistry strategy and actuator safety are separate layers
**ACCEPTED.** Allowed chemistry transition still requires fresh telemetry, thermal checks, envelope validation, OVP/OCP programming, readback, Output confirmation and watchdog coverage. Operational telemetry such as Vin does not become chemistry evidence merely because it is useful.

## D036 — universal `>~1%C plateau => HV veto` is rejected
**REJECTED / REMOVED.** High current can contribute to diagnostics together with U/T trajectory, regulation and cell evidence, but is not a one-number universal veto.

## D037 — 24–48 h post-heavy-charge rest is useful but not yet a lockout
**OPEN IMPLEMENTATION.** Treat as diagnostic/operator recommendation until Q006 is explicitly resolved.

## D038 — every production Manual text entry converges on one managed authority
**ACCEPTED / IMPLEMENTED.** Native V2 Manual and historic quick `V I` / `V I third-condition` text become `ManualSession` operations; raw unmanaged writes are not a production V2 authority path.

## D039 — active Manual reconfiguration is transactional, not live raw setpoint mutation
**ACCEPTED / IMPLEMENTED.** Changing V/I during active Manual uses verified Output OFF, retires the previous runner, then performs a fresh protected/readback-verified enable.

## D040 — historic `V I third` reach semantics are not contradictory inequalities
**ACCEPTED / IMPLEMENTED.** `15V` or `1.0A` means reach/cross that value. V2 tracks sample-to-sample crossing with a small tolerance and persists the target.

## D041 — controlled current probe exists but automatic trigger policy is not guessed
**ACCEPTED / IMPLEMENTED EXECUTOR.** The diagnostic executor can only lower current, gathers median U/I evidence, restores the exact prior current, and forces Output OFF if restoration/readback cannot be proven. Automatic policy stays disabled until Q005/Q014 are calibrated.

## D042 — structured dialogs outrank the global numeric Manual quick parser
**ACCEPTED / IMPLEMENTED.** A numeric payload is not automatically a Manual command when another explicit dialog owns the next message. Pending six-cell SG input bypasses the Manual middleware before parsing.

## D043 — Normal preserves the V1-compatible full automatic charge chain
**ACCEPTED / IMPLEMENTED.** `Normal` is not “no HV”. It may use bounded intermediate recovery and final Mix according to the same deterministic evidence/budget/timeout rules as the standard automatic charge. Standard recipe ceilings therefore include the chemistry’s ordinary recovery/Mix target (AGM 16.3, EFB/Ca 16.5), not expert extensions.

## D044 — Diagnostic is the explicit no-automatic-HV intent
**ACCEPTED / IMPLEMENTED.** `Diagnostic` can observe and conclude/stop without creating a new Recovery/Mix stage. It retains the Main/normal voltage envelope. This is the intent to choose when automatic HV must be structurally disabled.

## D045 — Recovery and Conditioning describe operator purpose, not permission to bypass evidence
**ACCEPTED / IMPLEMENTED FOUNDATION.** Recovery is an explicit restorative goal inside the standard recovery envelope; Conditioning is a service goal inside its envelope. Neither bypasses evidence, hard safety or diagnostic HV veto. Expert EFB 17.2–17.5 remains a separate, still-open workflow (Q011).

## D046 — AGM recovery budget is four attempts per session and does not force Mix when exhausted
**ACCEPTED / IMPLEMENTED.** Attempts #1–#4 may occur after confirmed AGM stuck plateau. A fifth confirmed plateau does not itself justify Mix; remain Main and require the normal tail or conservative 72 h rule. This preserves the deliberate “do not fry dry AGM mats” asymmetry.

## D047 — diagnostic HV veto is applied to the chosen transition, not guessed from raw evidence state
**ACCEPTED / IMPLEMENTED.** V2 first determines the intended authority action, then applies `BLOCK_AUTOMATIC_HV` to planned `ENTER_DESULFATION`/`ENTER_MIX`. This covers Normal, Recovery, Conditioning and timeout-generated Mix without accidentally blocking non-HV AGM step advances.

## D048 — production presentation must use production timing/intent semantics
**ACCEPTED / IMPLEMENTED.** Telegram previews/status and V2 timers must show Normal as full automatic, Diagnostic as no-auto-HV, and Mix fallbacks Ca20/EFB24/AGM10. Legacy rollback constants are not allowed to leak into the production operator contract.

## D049 — Auto Mix is a first-class direct-entry automatic program, not a new intent
**ACCEPTED / IMPLEMENTED.** Operator may explicitly start an automatic Mix-only program for Ca/Ca, EFB or AGM. It creates the session directly in `STAGE_MIX`; PREP, Main and intermediate Recovery/Desulfation are not entered even transiently. This is an entry/program mode, while `ChargeIntent` keeps describing charging purpose. Auto Mix uses the chemistry's standard Mix target (Ca/EFB 16.5 V, AGM 16.3 V), ~0.03C current, normal 120 s evidence blanking, mode-specific Delta confirmation, sticky 2 h finish hold, Ca20/EFB24/AGM10 fallback, SAFE_WAIT and Storage. It uses the normal recipe envelope only; expert EFB 17.2–17.5 V is not implicitly authorized. `Vbat < 12.0 V` rejects Auto Mix rather than silently falling back to PREP. Strong `BLOCK_AUTOMATIC_HV` diagnostic evidence and all ordinary V2 safety/readback/watchdog gates apply before Output enable.

## Current implementation checkpoints

- `1bd67cb...`: corrected RD telemetry, freshness/readback, 17.5V absolute envelope.
- `abfcbda...`: Cooling pause semantics, Ca/EFB session-wide recovery budget, Mix 20/24/10h.
- `0dbf744...` + `690f82d...`: hypothesis/SG/dynamic-loop evidence and durable storage.
- `085eb08...`: production V2 runtime safety aligned with Vin-as-diagnostics semantics.
- `a693090...` + `54fd424...`: native/unified Manual text authority, exact-reach compatibility, verified Manual reconfiguration and tests.
- `bb3ff05...` + `b68f943...`: structured SG dialog precedence over numeric Manual parser.
- `60d1bc96...`: V1-compatible AUTO intent/72h/AGM strategy plus atomic PREP skip.
- `44738236...`: production UI/tests aligned with the accepted AUTO semantics.
- `97a16efd...`: first-class transactional Auto Mix direct-entry program and Telegram workflow.

## Maintenance rule
Whenever behavior changes: update/add a numbered decision, update `CHARGE_STRATEGY.md` when production strategy changes, remove resolved items from `V2_OPEN_QUESTIONS.md`, add deterministic tests, and keep code/docs in the same change where practical.

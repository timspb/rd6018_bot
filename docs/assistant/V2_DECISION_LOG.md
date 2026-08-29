# V2 Decision Log

> Durable source of truth for decisions made after the V1 behavioral audit.
> Do not infer strategy from implementation details alone. If behavior changes, update this file with code/tests.

Status: **ACCEPTED** = target behavior; **IMPLEMENTED** = present on this branch; **OPEN** = unresolved; **REJECTED** = explicitly not intended.

## D001 — V1 is a multi-layer behavioral system
**ACCEPTED.** V2 must preserve/review operator UI, chemistry FSM, actuator sequencing, HA/RD readback, watchdogs, Manual/unmanaged paths, persistence/restore, diagnostics/logging. Reference: `V1_BEHAVIORAL_AUDIT.md`.

## D002 — Vin is PSU-health telemetry, not Pb FSM authority
**ACCEPTED / IMPLEMENTED.** `input_voltage` may be logged and used to diagnose the upstream PSU, but it does not grant/deny battery-stage authority and low/missing Vin is not itself a battery shutdown condition in production V2. `runtime_safety_v2.py` deliberately supersedes the older generic Vin kill while rollback code remains reproducible.

## D003 — Absolute V2 working-voltage ceiling is 17.5 V
**ACCEPTED / IMPLEMENTED.** `17.5 V` is accepted; anything above is rejected before hardware enable. Chemistry/intent recipes may impose lower limits. This is an outer envelope, not a default recovery target.

## D004 — BAT_MODE is observation, not permission
**ACCEPTED / IMPLEMENTED.** RD6018 decides whether its battery relay can close. V2 observes `BAT_MODE`; it does not require it as a software start permission.

## D005 — commanded, configured and measured values are distinct
**ACCEPTED / IMPLEMENTED FOUNDATION.** V2 distinguishes requested V/I/OVP/OCP, RD configured/readback values, and measured physical U/I. HA HTTP success alone is insufficient. Program -> readback -> verify -> Output ON -> verify again.

## D006 — raw RD telemetry semantics must be explicit
**ACCEPTED / IMPLEMENTED FOUNDATION.** Explicit CV/CC mode, raw protection status (`Normal/OVP/OCP/OPP`), corrected Pout/temp decode, model/serial/firmware, calibration/system state and HA source freshness are first-class telemetry. Legacy entities are migration fallbacks only.

## D007 — below ~12 V current remains small
**ACCEPTED.** `Vbat < ~12 V` keeps PREP-like ~0.01C treatment. Whether initial `Vbat >=12 V` atomically skips PREP is still Q001.

## D008 — Main normal-tail and stuck-plateau are separate evidence
**ACCEPTED.** A successful stable tail is not the same event as lack of progress. Slowly declining current is not a flat plateau.

## D009 — Ca/EFB recovery attempts are session-wide
**ACCEPTED / IMPLEMENTED.** Three bounded recovery attempts belong to the whole Main/recovery session. Progress does not reset the counter; only a new charge session does.

## D010 — after Ca/EFB recovery budget, next confirmed stuck plateau -> final Mix
**ACCEPTED / IMPLEMENTED.** Safety/thermal/telemetry faults still outrank this transition.

## D011 — AGM is intentionally conservative/asymmetric
**ACCEPTED.** AGM is not Ca/EFB with different constants. Preserve longer proof, staged Main, lower current emphasis and conservative HV behavior. Exact final AGM recovery budget remains Q009.

## D012 — 72 h Ca/EFB Main fallback is intentional legacy behavior
**ACCEPTED.** It covers non-completing trajectories distinct from fixed-current plateau recovery. Interaction with V2 intent is Q008.

## D013 — SAFE_WAIT 2 h is a maximum relaxation wait
**ACCEPTED.** Reach threshold earlier -> continue immediately. Otherwise continue after max 2h. Slow relaxation is diagnostic evidence, not automatically a fault.

## D014 — Mix delta is mode-specific
**ACCEPTED.** CV: `Imin -> confirmed ΔI rise`. CC: `Vmax -> confirmed ΔV fall`. Controlled variable is never treated as independent finish evidence.

## D015 — Mix needs spaced confirmations
**ACCEPTED.** Approximately 3 confirmations, ~60s spacing, with ~120s post-setpoint blanking.

## D016 — confirmed Mix delta starts sticky 2 h finish hold
**ACCEPTED / IMPLEMENTED.** Small later threshold recrossing does not erase the established event. Hard safety still wins.

## D017 — Mix fallback maxima are Ca 20 h / EFB 24 h / AGM 10 h
**ACCEPTED / IMPLEMENTED.** These are fallback observation maxima, not normal target durations. An already-started valid 2h finish hold owns normal completion.

## D018 — Done means managed Storage/float remains ON
**ACCEPTED.** Normal completion: `SAFE_WAIT -> Done/Storage -> ~13.8 V / 1 A -> Output ON`. Fault/hard-stop must be represented separately.

## D019 — Cooling is a pause, not a chemistry stage
**ACCEPTED / IMPLEMENTED.** Output OFF; exact source target preserved; active clocks frozen; recovery budget/AGM step/extrema/confirmed delta preserved; stuck plateau and incomplete delta continuity invalidated; sticky finish hold timer paused; state persisted/restorable.

## D020 — Manual is a first-class supported mode
**ACCEPTED / IMPLEMENTED FOUNDATION.** `ManualSessionManager` owns Manual output independently from the Pb chemistry FSM. Manual is not `Idle + Output ON` and is not legacy Custom chemistry authority.

## D021 — Manual working inputs are operator-defined; protections are not
**ACCEPTED / IMPLEMENTED.** Operator may define V/I and stop conditions. OVP/OCP are always derived from V/I and cannot be weakened manually. Backend Manual accepts up to 17.5 V and 12 A. Legacy five-step UI is currently only a compatibility input surface and still needs native V2 UX cleanup (Q002).

## D022 — Manual completion belongs to the operator, safety outranks everything
**ACCEPTED / IMPLEMENTED FOUNDATION.** Automatic Pb transitions (`plateau -> recovery`, `tail -> Mix`, chemistry timeouts, Storage transitions) do not run in Manual. Operator stop conditions (timer, V/I thresholds, optional mode-aware delta) own normal Manual completion. Hard thermal/electrical/readback/watchdog safety is non-bypassable.

## D023 — Manual Cooling preserves the exact manual program
**ACCEPTED / IMPLEMENTED.** At battery T >=40C Manual goes OFF/COOLING; active timer pauses; at <=35C the exact same V/I and freshly derived protections are safely re-applied; continuity-dependent delta proof resets. >=45C is terminal stop.

## D024 — Manual does not silently re-energize after process restart
**ACCEPTED SAFETY INVARIANT / IMPLEMENTED.** Persisted active/arming/cooling Manual state restores as `INTERRUPTED`; the saved request remains for review, but Output ON requires fresh operator re-authorization and normal safe-enable checks.

## D025 — Manual OFF / manual stop conditions are operator kill conditions
**ACCEPTED.** V>=, V<=, I>=, I<=, timer and equivalent Manual stop conditions are not chemistry evidence. For explicit Manual, they own normal stop behavior. Their remaining interaction with automatic-profile legacy `manual_off` compatibility is Q003.

## D026 — bank/cell fault inference must be hypothesis-specific
**ACCEPTED / FOUNDATION IMPLEMENTED.** Replace one generic “bad battery” score with hypotheses such as cell fault, self-discharge, sulfation, stratification, capacity loss, thermal abnormality and charger/path fault. V1 heuristic score remains evidence, never proof.

## D027 — Bank Fault becomes an active diagnostic contour
**ACCEPTED.** Diagnostics may request/perform bounded experiments to confirm/refute hypotheses. They may alter charge only in a safer/equal-energy direction (for example a controlled current reduction or OFF relaxation window), must restore prior setpoints transactionally, and must never invent extra HV merely to “test” a battery.

## D028 — confirmed cell-fault evidence may block further automatic HV
**ACCEPTED PRINCIPLE / THRESHOLDS OPEN.** Strong multi-signal evidence can deny the next automatic Recovery/Mix escalation. A heuristic score or a single SG/U/I sample cannot. Immediate unsafe thermal/electrical behavior remains hard-safety authority. Exact confirmation criteria are Q013.

## D029 — per-cell specific gravity is first-class external evidence
**ACCEPTED / IMPLEMENTED FOUNDATION.** For accessible flooded cells, store all six positions, raw SG, measurement temperature, timestamp, context, source and notes. Missing/inaccessible cells remain explicit `None`. A full-cell spread >=0.030 currently escalates to `VERIFY`, not “shorted cell”. Manufacturer/hydrometer-specific temperature correction must not overwrite the raw measurement.

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
**ACCEPTED.** Allowed chemistry transition still requires fresh telemetry, thermal checks, envelope validation, OVP/OCP programming, readback, Output confirmation and watchdog coverage. Conversely, operational telemetry such as Vin does not become chemistry evidence merely because it is useful.

## D036 — universal `>~1%C plateau => HV veto` is rejected
**REJECTED / REMOVED.** High current can contribute to diagnostics together with U/T trajectory, regulation and cell evidence, but is not a one-number universal veto.

## D037 — 24–48 h post-heavy-charge rest is useful but not yet a lockout
**OPEN IMPLEMENTATION.** Treat as diagnostic/operator recommendation until Q006 is explicitly resolved.

## Current implementation checkpoints

- `1bd67cb...`: corrected RD telemetry, freshness/readback, 17.5V absolute envelope.
- `abfcbda...`: Cooling pause semantics, session-wide recovery budget, Mix 20/24/10h.
- `0dbf744...` + `690f82d...`: hypothesis/SG/dynamic-loop evidence and durable storage.
- `085eb08...`: production V2 runtime safety aligned with Vin-as-diagnostics semantics.
- `1e11138...` + `57fbea3...`: first-class Manual authority wired into production V2; legacy Custom dialog becomes an input adapter only.
- `8b660b0...`: Manual contract tests; CI green on Python 3.10/3.11/3.12.

## Maintenance rule
Whenever behavior changes: update/add a numbered decision, update `CHARGE_STRATEGY.md` when production strategy changes, remove resolved items from `V2_OPEN_QUESTIONS.md`, add deterministic tests, and keep code/docs in the same change where practical.

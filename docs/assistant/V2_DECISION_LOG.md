# V2 Decision Log

> This is the durable record of decisions made after the V1 behavioral audit.
>
> Do not infer a new strategy from implementation details alone. If a decision changes, update this document in the same commit as the code/tests that implement the change.

Status labels:

- **ACCEPTED** — agreed target behavior;
- **IMPLEMENTED** — present on `refactor/pb-recovery-controller-v2` and expected to have tests;
- **OPEN** — not yet decided; see `V2_OPEN_QUESTIONS.md`;
- **REJECTED** — explicitly not the intended rule.

## D001 — V1 must be treated as a multi-layer behavioral system

**Status: ACCEPTED**

V2 migration is not “rewrite `charge_logic.py`”. The preserved contract includes:

- operator/UI state;
- chemistry FSM;
- physical actuator ordering;
- HA/RD readback;
- watchdogs;
- manual/unmanaged paths;
- persistence/restore;
- diagnostics and logging.

Reference: `V1_BEHAVIORAL_AUDIT.md`.

## D002 — Vin is PSU-health telemetry, not Pb FSM authority

**Status: ACCEPTED / IMPLEMENTED**

`input_voltage`/Vin may be displayed, logged and used to diagnose the RD6018 input supply, but battery charge-stage authority must not depend on it.

V2 output safety must fail closed on battery/output/control telemetry that actually determines safe charging, not turn a PSU-health sensor into chemistry evidence.

This supersedes older code/docs that treated `Vin < 60 V` as a general output-enable veto.

## D003 — RD6018 absolute manual/programmed voltage ceiling is 17.5 V

**Status: ACCEPTED / IMPLEMENTED**

The V2 absolute software ceiling is 17.5 V. Chemistry/intent recipe ceilings remain lower unless an explicit expert path authorizes a higher target.

This does **not** mean all EFB/Ca recovery programs should use 17.5 V. It is the outer controller envelope, not a default recipe.

## D004 — BAT_MODE is observation, not permission

**Status: ACCEPTED / IMPLEMENTED**

RD6018 battery mode may be collected for telemetry/diagnostics. It must not be treated as a prerequisite or authorization for starting a charge program.

## D005 — commanded, configured and measured values are different states

**Status: ACCEPTED / IMPLEMENTED FOUNDATION**

V2 must distinguish:

1. requested/commanded V/I/OVP/OCP;
2. RD6018 configured/readback V/I/OVP/OCP;
3. measured physical voltage/current.

A successful HA service call is not sufficient evidence that the controller is programmed correctly.

The safe-output path therefore programs, reads back, verifies within tolerance, enables Output, and verifies again.

## D006 — correct raw RD telemetry must be explicit

**Status: ACCEPTED / IMPLEMENTED FOUNDATION**

V2 telemetry foundation records/decode semantics including:

- explicit CV/CC state;
- raw protection code (`Normal/OVP/OCP/OPP`);
- corrected output-power decode;
- internal/external temperature distinction;
- model/serial/firmware where available;
- calibration/system state useful for diagnostics;
- telemetry freshness.

Legacy HA entities remain migration fallbacks only where the corrected V2 entity is not yet available.

## D007 — below 12 V, charge current must remain small

**Status: ACCEPTED**

The chemistry principle is preserved:

```text
Vbat < ~12 V -> PREP-like low-current treatment (~0.01 C)
```

The V1 one-tick logical PREP / physical Main mismatch is not a required behavior.

Whether initial `Vbat >= 12 V` should atomically start directly in Main is still an implementation/UX decision; see open questions.

## D008 — Main normal-tail and stuck-plateau logic are independent

**Status: ACCEPTED**

V2 must not collapse these into one generic “current low/high” rule.

- normal tail = successful end-of-Main evidence;
- stuck plateau = lack-of-progress evidence that may authorize a bounded recovery attempt.

A slowly continuing current decline is not the same as a flat plateau.

## D009 — Ca/EFB recovery attempts are a session-wide budget

**Status: ACCEPTED / IMPLEMENTED**

For one charging session, recovery attempts are counted across the whole Main/recovery loop.

Progress after a recovery attempt does **not** reset the counter.

Target behavior:

```text
plateau #1 -> recovery #1 -> Main
plateau #2 -> recovery #2 -> Main
plateau #3 -> recovery #3 -> Main
next confirmed plateau -> final Mix
```

The counter resets only on a new charging session.

Reason: the battery must not cycle indefinitely through recovery attempts at successive current plateaus.

## D010 — after exhausted Ca/EFB recovery budget, the next confirmed stuck plateau goes to final Mix

**Status: ACCEPTED / IMPLEMENTED**

Stopping solely because the bounded recovery budget is exhausted is not the intended legacy/recovery strategy. Final Mix is the remaining controlled recovery tool when the prerequisite evidence is still satisfied.

Safety/telemetry/thermal faults still outrank this transition.

## D011 — AGM is intentionally asymmetric and conservative

**Status: ACCEPTED**

AGM is not Ca/EFB with different voltage constants.

Dry/absorbed-mat AGM behavior requires a conservative strategy:

- reduce current as far as practicable before HV;
- use longer plateau confirmation;
- preserve staged Main voltage behavior;
- do not automatically copy flooded-battery recovery heuristics.

Any V2 change that makes AGM more aggressive requires explicit review.

## D012 — 72 h Ca/EFB Main -> Mix is a profile fallback, not a discovered V1 defect

**Status: ACCEPTED**

V1 already handles a genuinely stuck current earlier through plateau detection and intermediate recovery attempts.

The long Main timeout covers other non-completing trajectories such as extremely slow continuous progress.

Therefore it must not be removed merely because it “looks fail-open” when viewed without the earlier recovery loop.

Any future change to this fallback requires a separate strategy decision.

## D013 — SAFE_WAIT 2 h is maximum relaxation wait, not fault timeout

**Status: ACCEPTED**

After a high-voltage stage:

```text
if V reaches next-stage threshold early -> continue immediately
else -> wait at most 2 h -> continue anyway
```

Failure to cross the relaxation threshold within 2 h is diagnostic evidence, not automatic proof of a failed battery.

Do not convert SAFE_WAIT timeout into a generic fault state.

## D014 — Mix delta confirmation is mode-specific

**Status: ACCEPTED**

CV:

```text
Imin -> confirmed ΔI rise
```

CC:

```text
Vmax -> confirmed ΔV fall
```

Do not use current reversal as independent CC evidence; current is the controlled variable in CC.

## D015 — Mix requires three spaced confirmations

**Status: ACCEPTED**

A single threshold crossing is insufficient.

The target contract keeps approximately:

- 3 confirmations;
- ~1 minute class spacing;
- ~120 s blanking after a new setpoint before evidence is trusted.

## D016 — confirmed Mix delta starts a sticky 2 h finish hold

**Status: ACCEPTED / IMPLEMENTED**

After three valid confirmations the event is considered established.

Small subsequent movement back through the exact delta threshold does not erase the event or restart the proof from zero.

Hard safety events still override the active finish hold.

## D017 — Mix fallback maxima are Ca 20 h / EFB 24 h / AGM 10 h

**Status: ACCEPTED / IMPLEMENTED**

These are **maximum observation/fallback windows when no normal delta completion occurs**, not normal target durations.

```text
Ca/Ca  20 h
EFB    24 h
AGM    10 h
```

An already-started valid 2 h finish hold owns normal completion and is not cancelled merely because the fallback clock crosses its nominal maximum.

This supersedes V1 values (8/10/5 h) and any intermediate V2 documentation that listed EFB as 20 h.

## D018 — Done means managed Storage/float remains ON

**Status: ACCEPTED**

Normal program completion means:

```text
SAFE_WAIT -> Done/Storage -> ~13.8 V / 1.0 A -> Output ON
```

`Done` must not be silently redefined as hardware OFF.

A separate hard-stop/fault state is required when output is intentionally de-energized.

## D019 — Cooling is a pause in chemistry time, not a new evidence stage

**Status: ACCEPTED / IMPLEMENTED**

At thermal pause:

- output is OFF;
- source stage/target is preserved;
- active stage elapsed-time accounting is frozen;
- recovery budget is preserved;
- diagnostic extrema already established are preserved;
- uninterrupted continuity evidence is invalidated where OFF time makes it no longer valid;
- partial reversal-confirmation sequences are cleared;
- stuck-plateau proof must be re-established after resume;
- already-confirmed sticky finish hold remains confirmed, with its timer paused rather than erased.

Cooling state must be durably persisted so restart cannot silently resume a stale hot pre-Cooling state.

## D020 — raw manual operation is a supported product mode

**Status: ACCEPTED / NOT YET FULLY IMPLEMENTED**

Manual operation is not a debug escape hatch.

Target V2 design must expose an explicit MANUAL concept with richer operator inputs while keeping non-bypassable global safety/readback/watchdog authority.

The old semantic “controller Idle, but output may be ON” should be replaced with an explicit managed representation.

Exact manual schema is still open.

## D021 — Manual OFF remains an independent kill-condition system

**Status: ACCEPTED / PRIORITY DETAILS OPEN**

Persistent conditions such as V>=, V<=, I>=, I<= and timer remain useful and should survive the refactor.

They are operator stop conditions, not chemistry finish evidence.

Hard safety always outranks them. Their interaction with normal automatic stage completion/recovery is not yet fully specified.

## D022 — bank-fault/cell-fault inference must remain evidence-based

**Status: ACCEPTED PRINCIPLE / AUTHORITY OPEN**

V1 bank-fault risk is heuristic and must not be presented as proof of a specific failed cell.

V2 diagnostics should separate hypotheses and collect stronger evidence where possible, including longitudinal response, relaxation and controlled probes.

Whether a sufficiently strong deterministic cell-fault diagnosis gains authority to block further HV remains open.

## D023 — AI remains advisory only

**Status: ACCEPTED**

AI may explain traces, evidence and likely mechanisms. It does not choose or execute hardware setpoints and does not overrule deterministic safety/controller authority.

## D024 — higher-energy state means shorter blind-operation tolerance

**Status: ACCEPTED**

The V1 high-voltage fast watchdog principle is preserved:

```text
higher voltage / higher risk -> shorter maximum control/telemetry blind interval
```

V2 implementation may improve the exact watchdog architecture, but not weaken this invariant.

## D025 — chemistry strategy and actuator safety are separate layers

**Status: ACCEPTED**

A chemistry transition being allowed does not mean hardware may be enabled without:

- valid/fresh required telemetry;
- temperature checks;
- recipe/absolute envelope validation;
- protection programming;
- setpoint readback;
- Output state confirmation;
- watchdog coverage.

Conversely, a hardware sensor such as Vin should not be promoted into chemistry evidence merely because it is useful operational telemetry.

## D026 — the `>~1%C plateau => automatic HV veto` heuristic is rejected as a universal rule

**Status: REJECTED / REMOVED FROM CURRENT V2 AUTHORITY**

An absolute C-rate cutoff by itself is not sufficient evidence that a stable plateau represents a dangerous bank/cell fault.

The prior provisional V2 rule that automatically stopped recovery above about 1%C was too coarse and has been removed.

High current may contribute to diagnostics together with U/T trajectory, inability to regulate, cell-level evidence or other fault signals, but it is not a universal one-number veto.

## D027 — 1–2 day post-heavy-charge rest is a useful operational idea, not yet an FSM lockout

**Status: OPEN IMPLEMENTATION**

A rest period after aggressive recovery may be beneficial for evaluation and battery settling. The project has **not** yet decided to enforce a 24–48 h software lockout.

Until decided otherwise, treat this as an operator/diagnostic recommendation rather than a mandatory state transition.

## Implementation checkpoints on the current V2 branch

As of the commits immediately following the V1 audit:

### Telemetry / actuator foundation

Implemented in commit `1bd67cb875afeed4ae722a4e5fd335d6eecdd8cd`:

- corrected RD telemetry foundation;
- freshness model;
- protection decode including OPP;
- 17.5 V absolute ceiling;
- Vin removed from charge authority;
- readback-aware fail-closed output enable.

### Cooling / timing / recovery strategy

Implemented in commit `abfcbda97b947a73a474a3c11cb9d198b4bbf1f1`:

- Cooling evidence/time pause semantics;
- durable Cooling-related state handling;
- recovery-budget behavior aligned with the session-wide contract;
- Mix maxima updated to 20/24/10 h;
- coarse >1%C automatic HV veto removed.

## Maintenance rule

Whenever controller behavior changes:

1. update or add a numbered decision here;
2. update `CHARGE_STRATEGY.md` if production strategy changes;
3. update `V2_OPEN_QUESTIONS.md` if an open item is resolved;
4. add/modify deterministic tests;
5. commit docs and code together when practical.

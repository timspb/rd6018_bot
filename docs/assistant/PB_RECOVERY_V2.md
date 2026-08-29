# Pb Recovery Controller V2

## Status

V2 is the active production-design path on branch `refactor/pb-recovery-controller-v2`; `main` remains the audited V1 baseline until an explicit merge/deployment decision.

Use this source-of-truth order for strategy questions:

1. `V2_DECISION_LOG.md`;
2. `V2_OPEN_QUESTIONS.md`;
3. `CHARGE_STRATEGY.md`;
4. this architecture document;
5. `V1_BEHAVIORAL_AUDIT.md`.

## Design principle

Chemistry, operator intent, physical battery condition, control stage and hardware safety are separate dimensions.

```text
Physical battery + lifecycle
          |
Chemistry + Intent + Condition
          |
      Recipe envelope
          |
Telemetry -> SignalAnalyzer -> AUTO strategy -> diagnostic veto
                                      |
                                      v
                              stage/target decision
                                      |
                                      v
                             actuator safety
                                      |
                                      v
                                   RD6018
```

AI remains explanation-only and cannot own actuator decisions.

## Intent semantics

- **Normal** — V1-compatible full automatic charge. Standard intermediate recovery and final Mix are part of the ordinary chain when their evidence/budget rules say so.
- **Recovery** — explicit restorative purpose/context inside the same safety/evidence boundaries.
- **Conditioning** — service purpose inside its envelope. It does not bypass evidence or safety.
- **Diagnostic** — explicit no-automatic-HV intent; it may observe/finish/stop-and-diagnose but cannot create Recovery/Mix.

Thus “Normal” is not a low-voltage-only mode. Expert EFB > standard 16.5 V remains separate from these ordinary intent semantics.

## Authority boundary

Production composition:

- `AutoStrategyProductionChargeControllerV2` owns authoritative AUTO Main strategy, including 72 h fallback and production Mix timing;
- `DiagnosticProductionChargeControllerV2` adds hypothesis-specific veto of a planned new HV transition;
- legacy `ChargeController` remains a migration/rollback scaffold for mature mechanics but cannot independently own conflicting production Main/Mix decisions;
- `ProductionManualSessionManager` owns Manual independently from Pb chemistry;
- `V2RuntimeSafetyGuard`, configured-value readback, verified OFF and edge lease remain non-bypassable safety.

## AUTO startup

Initial stage is selected before first Output ON:

```text
Vbat < 12.0 V  -> PREP at small ~0.01C current
Vbat >= 12.0 V -> MAIN directly + PREP_SKIPPED audit
```

This removes the V1 one-tick logical/physical mismatch. Restore does not re-evaluate this startup shortcut; persisted stage/target owns restore.

## Sensor and setpoint model

- battery voltage = chemistry/FSM evidence;
- RD output voltage = physical source/output/watchdog evidence;
- `temp_ext` = battery temperature;
- `temp_int` = RD6018/controller/PSU temperature;
- Vin = PSU-health telemetry only, not Pb FSM authority;
- BAT_MODE = observation, not permission;
- CV -> current response (`Imin -> ΔI`);
- CC -> voltage response (`Vmax -> ΔV`).

V2 separates commanded, configured/readback and measured values. HTTP success is not proof that RD6018 accepted the desired state.

## Output enable invariant

Every managed enable obtains fresh telemetry, validates safety/envelope, programs derived OVP/OCP and V/I, verifies configured readback, arms edge safety, enables Output, and verifies the post-enable physical/configured state. Any unprovable step fails closed.

Absolute V2 software working-voltage ceiling = **17.5 V**. Ordinary chemistry recipes are lower; expert extensions require explicit workflow.

## Main evidence

Main has two distinct evidence problems:

- successful low-current tail;
- stuck-current plateau/lack of progress.

A slowly declining current is progress, not a plateau. A single C-rate number cannot prove a cell fault; the rejected `>~1%C => block HV` shortcut must not return.

## Recovery budgets

### Ca/Ca / EFB
Three recovery attempts belong to the entire charging session. Progress does not reset count. After attempts #1–#3, the next confirmed stuck plateau leads to final Mix unless safety/diagnostics veto the HV transition.

### AGM
AGM is deliberately more conservative:

- up to four intermediate recovery attempts per session;
- progress does not reset count;
- after attempt #4, another plateau does not force Mix;
- remain Main and require the normal low-current tail or the conservative 72 h rule;
- REHYDRATED state is diagnostic/lifecycle context, not an automatic transition modifier.

## 72 h Main fallback

This is production **strategy**, not generic hard safety:

- Ca/Ca/EFB + Normal/Recovery/Conditioning -> final Mix at 72 h even if no fixed plateau formed;
- AGM -> Mix at 72 h only when already CV with `I <= 0.20 A`; otherwise stop-and-diagnose;
- Diagnostic -> stop-and-diagnose, never timeout-generated HV.

The preserved legacy scaffold retains historical timeout code for rollback reproducibility. Production V2 masks that scaffold timeout during authoritative Main so the explicit V2 decision owns the result.

## Mix evidence

- CV: track `Imin`, confirm meaningful `ΔI` rise.
- CC: track `Vmax`, confirm meaningful `ΔV` fall.
- use multiple spaced confirmations.
- confirmed delta starts sticky ~2 h finish hold; hard safety still overrides.

Fallback maxima in production V2:
- Ca/Ca 20 h;
- EFB 24 h;
- AGM 10 h.

These are fallback observation maxima, not ETA.

## Diagnostic actuator authority

The strategy first chooses a concrete action. The diagnostic layer then inspects that action. `BLOCK_AUTOMATIC_HV` may convert a planned `ENTER_DESULFATION` or `ENTER_MIX` into stop-and-diagnose, including Normal and timeout-generated Mix. A normal AGM Main voltage-step is not an HV escalation and must not be vetoed as such.

Diagnostic inference cannot itself create a hard emergency stop; immediate unsafe U/I/T/protection/readback/watchdog behavior remains hard-safety authority.

## SAFE_WAIT / Cooling / Done

SAFE_WAIT after HV is Output OFF relaxation:

```text
threshold reached early -> continue immediately
otherwise -> max ~2 h -> continue anyway
```

Slow relaxation is diagnostic evidence, not a fault timeout.

Cooling is a pause in active chemistry time: output OFF, exact stage/target retained, active clocks frozen, session budgets and established extrema retained, continuity-dependent incomplete evidence reset, durable restore required.

Normal program completion preserves V1:

```text
Done/Storage = ~13.8 V / 1.0 A / Output ON
```

Safety stop OFF is not Done.

## Manual

Manual is a real supported authority mode, not legacy Custom chemistry or `Idle + Output ON`.

- user owns V/I and normal stop conditions;
- OVP/OCP are derived and non-overridable;
- working envelope up to 17.5 V / 12 A;
- automatic Pb transitions do not execute;
- Cooling pauses/resumes exact Manual program;
- active reconfiguration uses verified OFF -> fresh safe-enable;
- restart restores active Manual as `INTERRUPTED`, never silently re-energizes;
- historic `V I` and `V I third` are routed into managed Manual authority.

## RD telemetry / diagnostics

Corrected V2 telemetry includes explicit protection status (`Normal/OVP/OCP/OPP`), CV/CC, corrected Pout/temp decode, freshness, model/serial/firmware and read-only calibration/system context.

Bank Fault is hypothesis-specific, not one generic score. Per-cell SG is first-class external evidence; a first spread >=0.030 is imbalance/stratification evidence, not short-cell proof. RD displayed `V/I` is not battery internal resistance. Controlled two-wire `ΔV/ΔI` is stored only as a dynamic-loop response and compared longitudinally only under known connection identity.

Bounded diagnostic experiments may only move energy safer/equal; they must restore setpoints transactionally and must never raise HV merely to test a hypothesis.

## Physical battery registry

Longitudinal evidence is tied to a physical battery: chemistry/capacity, manufacturer/model, lifecycle condition, refill history, capacity/CCA/external Ri where available, recovery traces, SG and dynamic-loop observations. Prefer compare-with-self trends over universal one-number judgments.

## Watchdogs and rollback

Preserve:

```text
higher-energy state -> shorter permitted blind-operation interval
```

Readback, verified OFF and edge safety lease are safety infrastructure, not chemistry.

Production entrypoint remains `python bot.py`. `V2_UI=0` and `V2_AUTHORITATIVE=0` preserve controlled rollback paths; rollback code is not the production strategy source of truth.

## Testing / hardware validation

CI compiles and runs deterministic tests on Python 3.10/3.11/3.12. Coverage includes AUTO authority, intent envelopes, startup boundary, 72 h fallback, AGM/Ca/EFB budgets, Mix evidence/timers, Manual, telemetry/readback, edge lease, diagnostics and UI.

Hardware/on-device smoke is still mandatory before `main` merge: deterministic tests cannot prove the deployed ESPHome register mapping, relay path, connection-loss behavior or real battery response.

## Maintenance rule

If architecture changes, update this file **and** the numbered decision/open-question documents. Do not let implementation drift become the new strategy by accident.

# Pb Recovery Controller V2

## Status

V2 is the active production-design path on branch `refactor/pb-recovery-controller-v2`; `main` remains the audited V1 baseline until an explicit merge/deployment decision.

For strategy questions, use the documentation hierarchy in `docs/assistant/README.md`.

Most important companion documents:

- `V1_BEHAVIORAL_AUDIT.md` — what V1 actually did;
- `V2_DECISION_LOG.md` — accepted/rejected V2 decisions;
- `V2_OPEN_QUESTIONS.md` — intentionally unresolved questions;
- `CHARGE_STRATEGY.md` — concise current V2 strategy.

## Design principle

Chemistry, operator intent, physical battery condition, control stage and hardware safety are separate dimensions.

```text
Physical battery + lifecycle
          |
          v
Chemistry + Intent + Condition
          |
          v
Recipe envelope
          |
Telemetry -> SignalAnalyzer -> V2 authority
          |                     |
          |                     v
          +--------------> stage decision
                                |
                                v
                  ProductionChargeControllerV2
                                |
                                v
                    fail-closed actuator layer
                                |
                                v
                             RD6018
```

AI remains explanation-only and cannot own actuator decisions.

## Domain

### Chemistry

- AGM
- EFB
- Ca/Ca
- Flooded
- Custom

### Intent

- Normal
- Recovery
- Conditioning
- Diagnostic

### Condition

- Unknown
- Healthy
- Sulfated suspected
- Dry suspected
- Rehydrated
- Overwet suspected
- Stratified suspected
- Degraded

The domain deliberately allows contexts such as:

- `AGM + HEALTHY + NORMAL`;
- `AGM + REHYDRATED + RECOVERY`;
- `EFB + STRATIFIED_SUSPECTED + CONDITIONING`.

## Authority boundary

### V2-owned

For non-Custom V2-controlled paths:

- Main evidence interpretation;
- AGM Main step evidence;
- permission/denial of intermediate recovery;
- permission/denial of final Mix/HV;
- Mix CV `Imin -> ΔI` evidence;
- Mix CC `Vmax -> ΔV` evidence;
- sticky 2 h finish hold;
- recovery-attempt budget accounting;
- evidence continuity rules across Cooling;
- fail-closed behavior when the V2 evidence path itself cannot safely decide.

### Legacy scaffold retained during migration

The mature V1 layer is still reused where appropriate for mechanics that are not yet independently replaced, including portions of:

- telemetry validation;
- temperature safety;
- SAFE_WAIT mechanics;
- session persistence/restore;
- logging/statistics compatibility.

During V2-authoritative Main/Mix, legacy transition triggers are masked so they cannot independently escalate or finish the stage.

### Custom / Manual

Legacy Custom and V1 unmanaged manual output are distinct historical concepts.

The target product decision is that **Manual is a real supported mode**, but the explicit V2 MANUAL schema/restore contract is still under design. See `V2_OPEN_QUESTIONS.md`.

## Sensor model

### Battery vs output voltage

- battery voltage = chemistry/FSM evidence;
- RD output voltage = physical source/output measurement and hardware-watchdog evidence.

### Temperature

- `temp_ext` = battery temperature;
- `temp_int` = RD6018/controller/PSU temperature.

### Vin

`input_voltage`/Vin is PSU-health telemetry only. It is intentionally **not** a Pb chemistry/FSM authority signal and is no longer a general V2 output-enable veto.

### BAT_MODE

Observed for diagnostics only. It does not authorize charging.

### Control mode

Production semantics require explicit CV/CC where available:

- CV -> current response (`Imin -> ΔI`);
- CC -> voltage response (`Vmax -> ΔV`).

## RD telemetry foundation

The V2 branch adds a corrected/normalized telemetry layer rather than trusting every legacy HA entity name/scale as self-defining.

It covers:

- explicit CV/CC state;
- protection code including OPP;
- corrected output power;
- internal/external temperature distinction;
- model/serial/firmware metadata where available;
- calibration/system-state diagnostics;
- freshness metadata;
- migration fallback to legacy entities when the new corrected entities are not yet present.

Relevant files include:

- `rd6018_telemetry.py`;
- `esphome/rd6018_telemetry_v2.yaml`;
- `hass_api.py`;
- telemetry contract tests.

## Setpoint truth model

V2 explicitly separates:

1. **commanded** value — what the controller requested;
2. **configured/readback** value — what RD6018/HA reports as programmed;
3. **measured** value — physical output/battery telemetry.

A successful HTTP service call does not prove the RD6018 accepted the desired state.

## Output enable invariant

Every V2-safe enable path must:

1. obtain fresh required battery/output/safety telemetry;
2. validate battery plausibility and temperatures;
3. reject already-tripped protection or inappropriate Output state;
4. validate recipe and absolute voltage/current envelope;
5. program OVP;
6. program OCP;
7. program voltage;
8. program current;
9. verify readback of all programmed values;
10. re-check safety using fresh telemetry;
11. enable Output;
12. verify Output ON, protection state, temperature state and programmed readback;
13. force OFF on any failed step.

The absolute V2 software voltage ceiling is **17.5 V**. Normal chemistry/intent recipes remain lower unless an explicit expert workflow is designed and authorized.

## Main evidence

V2 preserves the V1 discovery that Main contains two separate evidence problems:

- successful low-current tail;
- stuck-current plateau / lack of progress.

A slowly declining current is progress, not a plateau.

A single C-rate number is not sufficient proof of a bank/cell fault. The temporary early-V2 heuristic “plateau above ~1%C => automatically forbid HV” was rejected and removed from current authority.

## Recovery budget

For Ca/Ca/EFB the accepted model is a session-wide bounded attempt budget:

```text
confirmed plateau -> recovery #1 -> Main
later confirmed plateau -> recovery #2 -> Main
later confirmed plateau -> recovery #3 -> Main
next confirmed plateau -> final Mix
```

Intermediate progress does not reset the count. A new charging session does.

AGM remains deliberately more conservative; final AGM budget details are still an explicit open question rather than copied from Ca/EFB.

## Mix evidence

### CV

Track `Imin`, then confirm a meaningful `ΔI` rise.

### CC

Track `Vmax`, then confirm a meaningful `ΔV` fall.

### Confirmation

The intended contract keeps multiple spaced confirmations rather than one crossing.

### Sticky finish hold

After the mode-specific delta is confirmed, a sticky ~2 h finish hold starts. Small later movement back through the exact threshold does not erase the already-confirmed event. Hard safety still overrides the hold.

### Fallback maxima

Current accepted V2 Mix maxima:

- Ca/Ca: 20 h;
- EFB: **24 h**;
- AGM: 10 h.

These are fallback observation maxima when normal evidence does not finish the stage. They are not target durations or ETA.

## SAFE_WAIT

After HV, Output is OFF while voltage relaxes toward the next lower-energy target.

Contract:

```text
threshold reached early -> continue immediately
otherwise -> wait at most ~2 h -> continue anyway
```

The maximum wait prevents an indefinite stall. Failure to cross the threshold by 2 h is diagnostic evidence, not automatic proof of battery failure.

## Cooling

Cooling is modeled as a **pause in chemistry time**, not a new evidence segment that should consume timers.

Accepted semantics:

- Output OFF;
- prior stage/target retained;
- active stage clocks paused;
- session recovery budget retained;
- established extrema retained for diagnostics;
- continuity-dependent evidence invalidated as needed;
- partial reversal confirmations cleared;
- stuck plateau must be re-proved after resume;
- already-confirmed sticky finish hold remains confirmed with its clock paused;
- Cooling is persisted durably for restart safety.

## Done / Storage

Normal program completion preserves the V1 contract:

```text
Done/Storage = ~13.8 V / 1.0 A / Output ON
```

A safety stop requiring Output OFF is not semantically equivalent to Done.

## Watchdog model

The architecture preserves the V1 principle:

```text
higher-energy state -> shorter permitted blind-operation interval
```

High-voltage loss of control/telemetry must cause a faster protective disconnect than ordinary low-energy telemetry loss.

## Physical battery registry

V2 supports saved physical batteries and longitudinal evidence such as:

- chemistry and nominal capacity;
- manufacturer/model;
- condition;
- refill/water history;
- cycles since refill;
- measured capacity;
- CCA;
- internal resistance;
- recovery-cycle traces/outcomes.

The intended diagnostic method increasingly compares one physical battery with its own prior behavior.

## Diagnostics direction

V1 bank-fault risk remains useful as a starting heuristic but not as proof of a specific cell failure.

V2 diagnostic work is intended to separate hypotheses and may add:

- relaxation analysis;
- capacity/CCA/Ri correlation;
- per-cell operator measurements;
- controlled bounded `ΔI -> ΔV` response probes;
- repeated-cycle comparison.

The exact threshold at which a deterministic diagnosis may block future HV is still open.

## Telegram workflow

Current V2 UI supports a path broadly like:

```text
programs
  -> saved physical battery OR chemistry
  -> intent
  -> capacity/details as needed
  -> preview
  -> explicit Start
```

Operator UI must not expose machine reason codes as if they were user explanations.

## Rollback

Production entrypoint:

```bash
python bot.py
```

UI rollback:

```bash
V2_UI=0 python bot.py
```

Authority rollback:

```bash
V2_AUTHORITATIVE=0 python bot.py
```

Both:

```bash
V2_UI=0 V2_AUTHORITATIVE=0 python bot.py
```

The preserved legacy monolith remains available for diagnosis.

## Testing

CI compiles and runs the deterministic test matrix on Python 3.10, 3.11 and 3.12.

Important coverage areas include:

- fail-closed safe output and readback;
- corrected telemetry contracts;
- V2 Main/Mix authority;
- CV/CC evidence separation;
- sticky finish hold;
- Cooling pause/evidence behavior;
- recipe envelopes;
- recovery trace persistence/replay;
- battery registry;
- transactional startup and UI integration.

Hardware/on-device smoke remains required before deployment because deterministic tests cannot prove ESPHome register scaling, relay wiring or real battery response.

## Maintenance rule

If architecture changes, update this file **and** the numbered decision/open-question documents. Do not let implementation drift become the new strategy by accident.

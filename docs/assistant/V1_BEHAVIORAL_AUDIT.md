# V1 Behavioral Audit

> Purpose: factual reconstruction of the production V1 behavior on `main` before the Pb Recovery V2 refactor.
>
> Audit baseline: `main` commit `8d3e2af9c2f16721f3303579f12d4f39bcc98a13`.
>
> This document describes what V1 actually does. It is **not** a proposal for V2. Design decisions made after the audit live in `V2_DECISION_LOG.md`; unresolved questions live in `V2_OPEN_QUESTIONS.md`.

## 1. Why this audit exists

The V1 behavior is spread across several layers. Reading only `charge_logic.py` is insufficient because the physical output sequence, watchdog behavior, manual/unmanaged paths, persistence and diagnostics live elsewhere.

The effective system is:

```text
Telegram/operator input
        |
        v
bot.py / UI state
        |
        +----------------------+
        |                      |
        v                      v
ChargeController          Manual/unmanaged paths
(charge_logic.py)              |
        |                      |
        +----------+-----------+
                   v
          actuator dispatcher
          HA / RD6018 writes
                   |
                   v
               RD6018
                   |
                   v
           telemetry + safety
                   |
        +----------+-----------+
        |                      |
        v                      v
  controller FSM        watchdog/diagnostics
```

The important architectural conclusion from the audit is that a V2 rewrite must preserve or explicitly replace **behavioral contracts across all of these layers**, not merely reproduce stage names.

## 2. Source map

Primary V1 sources inspected during the audit:

- `charge_logic.py` — chemistry targets, stage FSM, timers, SAFE_WAIT, Cooling, session state, bank-fault risk;
- `bot.py` — Telegram control, actuator dispatch, manual/unmanaged operation, watchdogs, link-loss behavior, monitoring;
- `hass_api.py` — HA state reads and number/switch writes;
- `protection_utils.py` — current/OCP ordering rules;
- `charging_log.py` — stage/event/checkpoint history;
- `database.py` — sensor history;
- `ai_engine.py` — advisory snapshot only;
- `config.py` — entity mapping and global limits;
- `tests/` — executable evidence for intended edge cases.

Historical strategy notes used to distinguish intentional behavior from accidents:

- `docs/assistant/CHARGE_STRATEGY.md`;
- `docs/assistant/HISTORY.md`.

## 3. Sensor semantics

### 3.1 Battery voltage vs RD output voltage

V1 has two different voltage concepts and they must not be collapsed:

- `sensor.rd_6018_battery_voltage` is the battery-side voltage used by charge-stage chemistry decisions;
- live `voltage` / RD output voltage is used by hardware-oriented checks such as the high-voltage watchdog.

A V2 telemetry model must preserve this distinction.

### 3.2 Temperature semantics

- `temp_ext` = battery/external probe temperature. This is the chemistry temperature and the source for battery temperature compensation and battery thermal decisions.
- `temp_int` = RD6018/controller/PSU internal temperature. This is hardware protection only; it is **not** evidence that the battery itself is hot.

### 3.3 CV and CC

The correct control-mode model is explicit:

- CV: voltage is controlled, current is the response variable;
- CC: current is controlled, voltage is the response variable.

This matters especially in Mix:

- CV completion evidence uses `Imin -> ΔI`;
- CC completion evidence uses `Vmax -> ΔV`.

V2 must not use `not CV == CC` as a production truth when an explicit CC signal is available.

### 3.4 Vin

V1 contains start/runtime logic around RD6018 input voltage (`Vin`). During the audit this was reclassified correctly:

- Vin is **PSU/input-supply health telemetry**;
- it is not battery chemistry evidence;
- it should not be a Pb FSM authority signal.

V1 historically had a start check roughly equivalent to “if Vin is present and below ~60 V, block”, while missing/zero Vin could fail open. This is not a desired V2 battery-safety contract.

## 4. Global targets and limits

V1 global stage current ceiling:

```text
MAX_STAGE_CURRENT = 12.0 A
```

Normal protection convention:

```text
OVP = target voltage + 0.1 V
OCP = target current + 0.1 A
```

Desulfation/recovery historically uses a wider OCP margin (`target current + 1.0 A`).

### 4.1 PREP

- base voltage: 12.0 V plus temperature compensation;
- current: `0.01 C`;
- purpose: raise a low-voltage battery gently before Main.

### 4.2 Main

- current: `0.1 C`, capped at 12 A;
- Ca/Ca base voltage: 14.7 V;
- EFB base voltage: 14.8 V;
- AGM staged base voltages: 14.4 -> 14.6 -> 14.8 -> 15.0 V.

### 4.3 Intermediate recovery / Desulfation

- base voltage: 16.3 V;
- current: `0.02 C`;
- duration: 2 h;
- this is an intermediate service attempt used when Main current is stuck, not the final Mix stage.

### 4.4 Mix

- Ca/Ca: 16.5 V;
- EFB: 16.5 V;
- AGM: 16.3 V;
- current: `0.03 C`, capped at 12 A.

### 4.5 Done / Storage

V1 `Done` does **not** mean power output OFF.

Normal completion semantics are:

```text
program complete -> Storage/float -> 13.8 V / 1.0 A -> output ON
```

`Done` therefore means “main program finished, battery is held on managed float/storage”. Any V2 state model that interprets Done as de-energized would change production semantics.

## 5. Temperature compensation

V1 compensates **voltage only**, from `temp_ext`, around 25 °C:

```text
V_comp = V_base + k * (25 - temp_ext)
```

Coefficients:

- Ca/Ca: 0.018 V/°C;
- EFB: 0.018 V/°C;
- AGM: 0.016 V/°C;
- Custom: 0.018 V/°C.

Legacy correction is clamped to approximately ±0.60 V.

The implementation can also adjust a live stage target when battery temperature moves enough to cross the compensation hysteresis.

## 6. Automatic profile startup

V1 automatic profile capacity input is approximately 1..500 Ah.

Battery temperature start rule:

- external battery temperature below 10 °C blocks normal start.

### 6.1 Low-voltage start

The intended chemistry principle is simple:

```text
battery < 12 V -> small current first
```

PREP supplies that behavior at ~0.01 C.

### 6.2 Initial voltage >= 12 V quirk

V1 contains an architectural mismatch on startup when the battery is already >= 12 V:

- controller state begins in PREP;
- the physical target can be programmed immediately to the Main target;
- on the next controller tick PREP transitions logically to Main.

Thus logical state and physical setpoint can differ for one control interval.

This is an implementation quirk, not a chemistry requirement. Whether V2 should atomically skip PREP and start directly in Main at >=12 V is recorded as a separate design question.

## 7. Stage machine

V1 named stages:

```text
PREP
MAIN
DESULFATION
MIX
SAFE_WAIT
COOLING
DONE
IDLE
```

The effective automatic recovery chain is:

```text
PREP
  -> MAIN
       -> normal tail completion
       -> intermediate recovery attempts when current is stuck
       -> final MIX
  -> SAFE_WAIT
  -> DONE / Storage
```

For AGM, Main itself contains multiple voltage steps before final recovery/Mix decisions.

## 8. PREP behavior

PREP target is approximately 12 V + temperature compensation at 0.01 C.

Transition:

```text
Vbat < 12 V -> stay PREP
Vbat >= 12 V -> enter MAIN
```

On transition V1:

- records the Main Ah anchor;
- resets stage evidence;
- starts ~120 s blanking after the new setpoint;
- programs the Main target.

## 9. Main: two independent evidence machines

A key V1 finding is that Main is not one timer. It contains two separate concepts:

1. **normal low-current tail completion**;
2. **stuck-current plateau recovery**.

Confusing these two produces incorrect conclusions about the 72 h Main fallback or the role of Desulfation.

### 9.1 Normal tail completion

#### Ca/Ca and EFB

Condition:

- confirmed CV;
- current below ~0.30 A;
- 3 h without a new lower current minimum.

A new lower current restarts the hold clock.

Important V1 nuance: the “new minimum” bookkeeping can be updated on a sample that itself is not CV, but actual completion still requires CV. This behavior is covered by tests and should not be casually changed without a replacement evidence model.

Normal Ca/EFB completion proceeds toward Mix under the legacy automatic-recovery strategy.

#### AGM

Condition:

- confirmed CV;
- current below ~0.20 A;
- 2 h hold.

If the current AGM voltage step is not the final 15.0 V step, V1 advances to the next Main voltage step. From the final step it can proceed to Mix according to the active profile strategy.

### 9.2 Stuck-current plateau recovery

This is a separate path.

#### Ca/Ca and EFB

Candidate plateau:

- CV;
- current >= ~0.30 A;
- current stops making a new lower minimum;
- plateau persists about 40 min.

A new lower current resets the plateau clock.

Example:

```text
0.60 -> 0.55 -> 0.50 -> 0.45 A
```

is progress, not a plateau.

A flat trajectory near 0.60 A for the required interval is a plateau candidate.

#### AGM

AGM uses a much more conservative plateau duration:

- CV;
- current >= ~0.20 A;
- plateau about 2 h before recovery escalation.

This asymmetry is intentional because AGM construction and dry-mat failure modes are different. AGM must not be treated as flooded Ca/EFB with different labels.

### 9.3 Intermediate recovery budget

When a qualifying Main plateau is confirmed, V1 can enter the intermediate 16.3 V / 0.02 C / 2 h service stage.

For Ca/Ca/EFB the accepted interpretation is a **session-wide recovery-attempt budget**:

```text
MAIN plateau -> recovery #1 -> MAIN progresses
later plateau -> recovery #2 -> MAIN progresses
later plateau -> recovery #3 -> MAIN
next confirmed plateau -> final MIX
```

Progress between attempts does **not** reset the count. The budget resets only for a new charging session.

This prevents a battery from cycling indefinitely between Main and service recovery at successively different current plateaus.

AGM has a separate, more conservative attempt policy in the legacy implementation.

## 10. Main hard timeout

V1 has a long Main maximum of approximately 72 h for standard automatic profiles.

For Ca/Ca and EFB, timeout can force transition to Mix. Historical project documentation explicitly records this as accepted behavior.

This must **not** be misclassified as “the only stuck-current handling”. Stuck current already has its own earlier plateau/recovery cycle. The 72 h fallback catches long Main trajectories that never satisfy normal completion but also never form the exact persistent plateau needed for the intermediate recovery rule, for example a current that continues to decline extremely slowly.

Therefore current project interpretation is:

- 72 h -> Mix is an intentional profile fallback;
- it is not, by itself, a V1 bug.

Custom uses its operator-specified time limit instead.

## 11. Intermediate recovery / Desulfation

Legacy intermediate recovery behavior:

```text
MAIN
  -> DESULFATION / service recovery
       16.3 V
       0.02 C
       2 h
  -> output OFF
  -> SAFE_WAIT
  -> MAIN
```

The return threshold is based on the next Main target minus about 0.5 V.

This stage is therefore a controlled high-voltage attempt embedded inside the Main/recovery loop, not merely a cosmetic “desulfation mode”.

## 12. SAFE_WAIT semantics

SAFE_WAIT is an output-OFF relaxation bridge between a high-voltage stage and the next lower-voltage target.

The important contract is:

- if voltage falls below the threshold early, continue immediately;
- otherwise wait at most about 2 h;
- at the 2 h maximum, continue to the intended lower-voltage stage anyway.

The 2 h limit is an **anti-stall maximum wait**, not a fault criterion.

Therefore:

```text
threshold not reached by 2 h != automatic battery fault
```

Slow relaxation can and should still be recorded as diagnostic evidence.

### 12.1 SAFE_WAIT diagnostic sampling

V1 also records post-charge relaxation samples, roughly around 5/10/15 min, and derives diagnostic information from voltage decay, slope, temperature spread and near-zero current behavior.

Longer V2 longitudinal storage may extend those windows, but the V1 completion semantics above should not be confused with diagnostic sampling.

## 13. Mix behavior

Mix has a ~120 s monitoring blanking period after target changes.

It tracks mode-specific extrema:

- CV -> current minimum `Imin`;
- CC -> voltage maximum `Vmax`.

### 13.1 CV finish evidence

Candidate reversal:

```text
I_now >= Imin + max(0.03 A, 30% * Imin)
```

### 13.2 CC finish evidence

Candidate reversal:

```text
V_now <= Vmax - 0.03 V
```

### 13.3 Confirmation rule

V1 requires multiple confirmations rather than one crossing:

- 3 confirmations;
- spaced about 60 s apart.

### 13.4 Sticky finish timer

After the reversal is confirmed, V1 starts a ~2 h finish timer.

The confirmed event is sticky: the signal does not have to remain beyond the exact delta threshold for the whole 2 h.

This was reviewed and accepted as a sensible contract because three spaced confirmations already make a transient threshold crossing unlikely to be accidental.

### 13.5 Legacy Mix fallback maxima

Original V1 fallback maxima were approximately:

- Ca/Ca: 8 h;
- EFB: 10 h;
- AGM: 5 h.

These were judged too short during the V2 review and are **not** the target V2 limits. See `V2_DECISION_LOG.md`.

## 14. Cooling behavior

Battery temperature thresholds in V1 are approximately:

- 35 °C: warning;
- 40 °C: pause / Cooling;
- 45 °C: critical stop.

At >=40 °C during an active managed charge, V1:

- remembers the source stage/target;
- enters Cooling;
- turns output OFF.

At <=35 °C it resumes the prior stage/target and turns output back on.

At >=45 °C it performs an emergency stop/reset toward Idle/OFF.

### 14.1 V1 implementation weakness: persistence

The audit found a persistence risk around the Cooling transition:

- some control paths can return after entering Cooling before the new state is durably saved;
- a crash/restart can therefore restore stale pre-Cooling state;
- startup restore historically lacks a full battery-temperature preflight before re-enabling output.

This is an implementation defect to fix in V2, not a reason to remove Cooling.

### 14.2 Evidence/timer ambiguity

V1 effectively resumes prior state with much of its evidence still present. The exact intended semantics for timers/evidence after a long Cooling pause were not explicit in V1 and required a V2 design decision. That decision is recorded separately.

## 15. Manual and unmanaged operation

V1 can energize the RD6018 while the managed controller remains Idle.

This is not merely a debug loophole; it is an actual operator manual mode.

Examples of V1 behavior:

- dashboard toggle with valid managed session can restore the session;
- dashboard toggle with no managed session can simply turn RD output ON using current device setpoints while controller remains Idle;
- direct text `V I` can write voltage/current directly;
- an additional condition can be attached to stop later.

Legacy raw manual writes do not necessarily run the same full OVP/OCP/readback/FSM transaction as managed profile starts.

This is a major V2 boundary: manual operation must remain available, but it needs an explicit, safety-enveloped model instead of accidental “Idle but output ON” semantics.

## 16. Manual OFF supervisor

V1 has an independent persistent stop-condition engine stored in `manual_off_state.json`.

Supported concepts include:

- `V >= x`;
- `V <= x`;
- `I <= x`;
- `I >= x`;
- timer;
- combinations;
- effectively exact window when lower and upper bounds coincide.

When the output is ON and a condition hits, V1 can log, notify, hard-stop and clear the condition.

Examples/presets include roughly:

- timer 2 h;
- I <= 0.30 A;
- V >= 16.2 V.

`manual_off_active` also suppresses some automatic time-based behavior in the legacy FSM. The exact desired priority relationship between Manual OFF and V2 automatic completion/recovery remains a separate design question.

## 17. Actuator sequencing

Controller decisions do not directly write RD registers. `bot.py`, `hass_api.py` and `protection_utils.py` form the physical actuator path.

Important existing sequencing rules:

### 17.1 Current decrease

When reducing current, V1 tends to lower current before tightening OCP.

### 17.2 Current increase

When increasing current:

1. raise OCP first;
2. wait briefly (~0.35 s);
3. raise current setpoint.

### 17.3 Startup current raise

A startup sequence can temporarily use a wider idle OCP, program current, enable output, allow settling, then restore the intended OCP.

### 17.4 Transition race weakness

Voltage transitions do not have an equally strong atomic interlock. A transition that simultaneously raises voltage and reduces current can momentarily execute in an undesirable order depending on the dispatcher path.

A V2 transactional actuator layer should explicitly order the whole envelope rather than rely on independent per-field writes.

## 18. Write acknowledgement and readback

Legacy `HassClient` generally knows whether HA returned a successful HTTP status, but upstream callers historically do not treat all writes as one transaction with rollback.

The audit established that RD configured values can be read back through HA/ESPHome entities.

The correct V2 model should distinguish three things:

1. **commanded** setpoint — what software requested;
2. **configured/readback** setpoint — what RD6018 reports is programmed;
3. **measured physical** value — battery/output telemetry.

These are not interchangeable.

## 19. Safety and watchdogs

### 19.1 Battery temperature

See Cooling thresholds above.

### 19.2 Internal PSU/controller temperature

`temp_int` near ~55 °C is a hard hardware-protection condition when charging/output is active.

### 19.3 OVP/OCP

Hardware protection triggers cause a hard stop in managed operation.

One legacy weakness is that some software hard-stop checks are conditioned on the controller being active, while unmanaged/manual output can exist in Idle. V2 manual mode must still inherit global protection authority.

### 19.4 High-voltage blind-operation watchdog

V1 uses a tighter watchdog budget when output voltage is high:

- normal controller tick/link watchdogs operate on minute-scale thresholds;
- above roughly 15 V, loss of control-loop progress can trigger a much faster emergency disconnect (about 60 s class).

The good architectural principle is:

```text
higher-energy state -> shorter allowed blind-operation interval
```

### 19.5 HA communication watchdog

If successful HA communication becomes stale for a few minutes, V1 can hard-stop.

### 19.6 Controller tick watchdog

If controller ticks stop progressing while output remains ON, V1 can hard-stop; the threshold is tighter for high voltage.

### 19.7 Link-loss handling weakness

The broad telemetry loop can treat a generic exception as “link loss”. That is operationally conservative but can misclassify internal software errors as network failure. V2 should separate transport freshness from internal exceptions.

## 20. Persistence and restore

V1 persists a `charge_session.json` document with a maximum useful age around 24 h.

Persisted state includes, depending on stage:

- profile and Ah limit;
- current stage;
- total/stage start times;
- Ah anchors;
- starting readings;
- recovery/desulfation attempt count;
- actual/target setpoints;
- AGM step index;
- SAFE_WAIT target/next-stage state;
- low-current hold evidence;
- stuck-current plateau evidence;
- previous stage/transition history.

Restore is used for:

- process restart;
- link recovery;
- output-already-on recovery;
- dashboard/session restore flows.

SAFE_WAIT restore keeps output OFF.

The persistence system is therefore part of the FSM contract; it cannot be replaced with only `stage=<name>`.

## 21. Bank-fault risk detector

V1 contains a heuristic/event-based risk detector for likely bank/cell problems. Signals include combinations such as:

- low starting voltage;
- slow PREP behavior;
- unusually long Main;
- poor voltage rise / Ah response;
- temperature rise with weak voltage progress;
- fast SAFE_WAIT decay;
- suspicious tail behavior.

It is primarily diagnostic/advisory in V1.

Important audit conclusion: this is **not** proof of a specific failure such as a shorted cell. The V2 role of bank-fault evidence — advisory only vs deterministic authority to block further HV — remains a design question.

## 22. Post-charge diagnostics

V1 SAFE_WAIT/post-charge analysis derives heuristic evidence such as:

- voltage drop over time;
- voltage slope;
- temperature span;
- near-zero-current confirmation;
- confidence/risk labels.

A self-discharge style warning can be generated when voltage is low and falling quickly (for example around V <13.5 V and a very large negative V/h slope).

These are useful diagnostics but not chemistry proofs by themselves.

## 23. AI boundary

V1 AI/LLM logic is advisory only.

It receives a rich snapshot including stage, targets, timers, temperature compensation, Mix evidence and recent telemetry, but it does not own actuator setpoints or stage transitions.

This separation is a contract worth preserving:

```text
deterministic controller owns hardware
AI explains evidence
```

## 24. Logging and telemetry history

V1 maintains several parallel observability channels:

- charge event log with rotation;
- stage-end duration/Ah/trigger records;
- periodic checkpoints;
- SQLite sensor history, roughly 30 s sampling and ~30 d retention;
- separate informational charge monitor.

The separate monitor contains simplistic rules such as “V >=13.5 and I <0.1 A looks finished”. During a managed chemistry program this can contradict the real FSM. V2 already treats this as a legacy side-channel that must not override managed stage evidence.

## 25. Behaviors that were initially suspected but are NOT V1 defects

The audit deliberately corrected several earlier misclassifications.

### SAFE_WAIT 2 h timeout

Not a fail-open safety bug. It is a maximum relaxation wait before proceeding to a lower-energy target.

### Ca/EFB 72 h Main -> Mix

Not the only stuck-current mechanism and not automatically a bug. Stuck-current recovery happens earlier via intermediate service cycles; 72 h is a separate fallback for pathological slow progress.

### AGM asymmetry

Not accidental inconsistency. AGM needs a different strategy because dry/absorbed electrolyte construction changes the acceptable recovery behavior.

### Final Mix after exhausted Ca/EFB recovery attempts

Not an accidental escalation. The accepted strategy is to prevent endless Main/recovery cycling and eventually use final electrolyte mixing when the bounded recovery budget has been exhausted.

## 26. V1 implementation weaknesses that V2 should explicitly replace

The main implementation weaknesses found during audit are:

1. logical PREP / physical Main mismatch when initial V >=12 V;
2. non-transactional multi-setpoint actuator changes;
3. incomplete write/readback/rollback semantics in legacy paths;
4. potential voltage/current ordering races across stage changes;
5. Cooling persistence/restore gap;
6. incomplete temperature preflight on restore/re-enable paths;
7. unmanaged/manual output living outside an explicit controller state;
8. software protection checks that may depend on managed-controller activity while manual output can be ON;
9. broad exception -> link-loss classification;
10. legacy informational completion heuristics that can contradict managed chemistry logic;
11. some historical paths infer mode from `!CV` instead of requiring explicit CC evidence.

These are implementation concerns. They should not be “fixed” by silently changing chemistry strategy.

## 27. V1 contracts that must not be lost accidentally

Any V2 migration should explicitly preserve or consciously supersede the following:

- low-current PREP below ~12 V;
- separate normal-tail and stuck-plateau evidence in Main;
- intermediate recovery cycles before final Mix;
- session-wide bounded recovery attempts;
- conservative AGM-specific behavior;
- CV/CC-specific Mix evidence;
- 3 spaced reversal confirmations;
- sticky 2 h finish hold;
- SAFE_WAIT early threshold + 2 h maximum wait semantics;
- Done = managed Storage/float ON;
- battery vs PSU temperature distinction;
- physical battery voltage vs RD output voltage distinction;
- persistent session restore;
- high-voltage fast watchdog;
- manual operator control as a supported product feature;
- independent Manual OFF kill conditions;
- AI advisory-only authority boundary;
- post-charge evidence collection.

## 28. Relationship to V2 documents

Read next:

1. `V2_DECISION_LOG.md` — decisions accepted after this audit and their implementation status;
2. `V2_OPEN_QUESTIONS.md` — deliberately unresolved strategy questions;
3. `CHARGE_STRATEGY.md` — concise production V2 strategy;
4. `PB_RECOVERY_V2.md` — V2 architecture and rollout details.

When those documents disagree, the source-of-truth priority is defined in `docs/assistant/README.md`.

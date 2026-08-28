# Pb Recovery Controller V2

## Goal

Evolve the bot from a profile/timer charger into an evidence-driven Pb recovery controller without discarding the existing `ChargeController` FSM.

The central rule is that **chemistry, charge intent, battery condition and safety are different dimensions**. A generic `AGM` label must not imply whether the battery is healthy, dry, recently rehydrated, being normally charged or undergoing an expert recovery cycle.

## Architecture

```text
Battery Registry / Lifecycle
        |
Telemetry -> SignalAnalyzer -> deterministic evidence
        |                         |
        |                         v
        |                  State / trend model
        |                         |
        +-----------------> RecipeEngine
                                  |
                                  v
                         ChargeController FSM
                                  |
                                  v
                         SafetySupervisor
                                  |
                                  v
                               RD6018
```

AI is an explanation layer only. It must not own voltage/current decisions.

## Domain model

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

A battery can therefore be `AGM + REHYDRATED + RECOVERY`, which is intentionally different from `AGM + HEALTHY + NORMAL`.

## Signal model

The controller should reason about trajectories, not isolated thresholds. The first implementation extracts:

- `dU/dt`
- `dI/dt`
- `dT/dt`
- CV current minimum (`Imin`)
- current plateau
- current reversal after `Imin`
- voltage sag during current reversal
- thermal acceleration during current reversal

A current increase after a well-defined CV minimum is **not automatically a fault**. It is end-of-charge evidence only when voltage remains near target and temperature/current dynamics remain benign. A rising current together with accelerating temperature or loss of target voltage is treated as suspicious evidence instead.

## Safety model

Recipe limits are not the same as absolute controller limits.

The model therefore separates:

- requested target voltage/current;
- recipe voltage ceiling;
- absolute controller voltage/current ceiling;
- OVP/OCP envelope.

This permits an explicit expert EFB conditioning recipe to use (for example) 17.5 V while still preventing an AGM recipe capped at 16.3 V from accidentally requesting 16.4 V.

### Output enable invariant

Every future output-enable path must converge on one fail-closed transaction:

1. read required live telemetry;
2. reject missing/invalid battery voltage, current, external battery temperature, input voltage, protection state or output state;
3. validate recipe and absolute limits;
4. program OVP;
5. program OCP;
6. program voltage;
7. program current;
8. read all four values back;
9. re-run preflight because temperature/input/protection state may have changed;
10. enable output;
11. verify output state and protection state;
12. force OFF on any failed step.

No manual override, recovery recipe or Telegram shortcut may bypass this layer.

## Recovery history (next layer)

Persist longitudinal evidence per physical battery rather than only per charge session:

- water added total/per cell;
- cycles since refill;
- measured capacity;
- CCA;
- internal resistance;
- `Imin` at main voltage;
- `Imin` and current reversal at high-voltage stage;
- time to target voltage;
- `Tmax` and maximum `dT/dt`;
- relaxation voltage at 5m/15m/1h/12h/24h.

The eventual recovery score must be explainable and trend-based; it must compare the battery primarily with its own previous cycles rather than a single manufacturer table.

## Migration plan

1. Add domain types, signal analysis and fail-closed safety primitives (this change).
2. Route all output-enable paths through `SafeOutputCoordinator`.
3. Feed `SignalAnalyzer` from the live logger and expose evidence to `ChargeController` without changing existing recipes yet.
4. Split recipe selection by chemistry + intent + condition.
5. Add battery registry/lifecycle persistence and recovery history.
6. Introduce explicit expert conditioning recipes (including EFB current-driven mixing) behind operator opt-in.
7. Add trace-replay tests based on real charge logs.

## Non-goals for phase 1

- Do not remove the existing AGM staged Main profile.
- Do not globally ban 16.3/16.5 V recovery stages.
- Do not silently increase any existing voltage target.
- Do not let AI choose hardware setpoints.
- Do not treat manufacturer consumer-mode recommendations as the only empirical source of Pb recovery behavior.

# Mix Adaptive Current Containment

Status: **ACCEPTED DESIGN DECISION / NOT YET IMPLEMENTED**

This note records the accepted safety mechanism for a future V2 Mix implementation. It is intentionally separate from Mix finish calibration: the containment mechanism is useful even if the exact `Imin -> ΔI` finish detector changes after real-battery characterization.

## Purpose

During a high-voltage Mix stage, once the battery has demonstrated a confirmed lower current minimum, the hardware current ceiling should be tightened dynamically. The purpose is to reduce the amount of current/power the battery can suddenly accept if the remote control path (bot / HA / network) becomes unavailable while the RD6018 remains energized.

This is a containment layer, not a chemistry-completion criterion and not a replacement for verified Output OFF, the edge safety lease/watchdog, thermal limits, or ordinary electrical protections.

## Core invariant

Adaptive containment may only remove current authority. It must never add authority.

For one Mix session:

```text
0 < I_adaptive <= I_programmed <= I_recipe
I_adaptive(t+1) <= I_adaptive(t)
```

In particular, an adaptive calculation can never raise the current above the currently programmed setpoint. If the operator/session has already selected a lower current than the recipe ceiling, that lower programmed value remains the hard upper bound.

Conceptually:

```text
I_adaptive_new = min(
    I_programmed_current_ceiling,
    I_adaptive_previous,
    Imin_confirmed + containment_headroom
)
```

`containment_headroom` must be larger than the Mix finish/reversal delta by a calibrated margin so that the protection does not clip the very `Imin -> ΔI` signal the controller is trying to observe. Exact coefficients are deliberately **not selected yet**.

An equivalent calibrated form may use a multiplier over the required reversal delta, for example `Imin + K * ΔI_required` with `K > 1`; the exact formulation remains empirical. Regardless of formulation, the result is always clamped by the existing programmed current ceiling and by the previous adaptive ceiling.

## Scale with battery capacity

Chemistry/evidence thresholds must not be defined as one universal absolute ampere value. A 1 A Mix current means ~0.014C for a 72 Ah battery but ~0.11C for a 9 Ah battery.

Therefore the future calibrated reversal/headroom model should distinguish:

- battery-scale evidence, expressed primarily in C-rate and/or relative change from `Imin`;
- hardware measurement resolution/noise, which is inherently an absolute-current floor;
- the recipe/program current ceiling, which remains independent authority and can only be tightened by containment.

A generic future evidence form may therefore be based on:

```text
ΔI_required = max(
    hardware_measurement_floor,
    capacity_scaled_delta,
    relative_delta_from_Imin
)
```

No production constants are accepted by this note; Q005/Q014 physical characterization remains responsible for real thresholds/noise/settling.

## Ratchet semantics

The adaptive ceiling is monotonic within one Mix session.

Example only:

```text
initial programmed ceiling  2.16 A
confirmed Imin              1.20 A -> tighten ceiling
later confirmed Imin        1.00 A -> tighten again
later confirmed Imin        0.91 A -> tighten again
```

A later temperature/current excursion must not automatically loosen the already-earned containment. Raising the ceiling requires a new explicit authority decision/session transition, not ordinary Mix telemetry.

This gives the desired safety property: as the battery progresses deeper into Mix and demonstrates that it can operate at lower current, the maximum energy available to an uncontrolled acceptance increase decreases as well.

## Current-ceiling reach is censored evidence

If the battery current rises until the RD6018 reaches the adaptive current ceiling, the controller can no longer observe the unconstrained current rise. The supply may transition from CV to CC and reduce actual voltage below the Mix target.

Therefore:

```text
CURRENT_CEILING_REACHED
```

must be represented explicitly. It must **not** be interpreted as `current stopped rising`, `flat current`, or failure to confirm reversal. It means only that battery acceptance reached at least the allowed ceiling.

The finish detector must use CV/CC state, actual V/I, temperature trend, prior confirmed `Imin`, and the fact that the signal is ceiling-limited.

## Protection sequencing

When the adaptive current ceiling is tightened, OCP/readback sequencing must preserve the existing actuator-safety rules. The software must not create an OCP value so close to the current setpoint that normal noise causes nuisance trips, and it must not weaken any existing protection.

All current/setpoint changes remain subject to configured-value readback and the established protected-write ordering.

## Network-loss containment model

The intended layered behavior is:

```text
Mix recipe/program current ceiling
        ↓
confirmed lower Imin
        ↓
adaptive monotonic current ratchet written to RD6018
        ↓
remote control path fails
        ↓
RD6018 still has the tighter local current ceiling
        ↓
edge lease/watchdog timeout
        ↓
verified Output OFF
```

Thermal and hard electrical safety remain independent layers. Adaptive current containment reduces the immediate consequence of a lost control plane; it does not authorize indefinite high-voltage operation at the reduced current.

## Implementation gate

Before implementation, define and test:

1. what constitutes a **confirmed** new `Imin` rather than a local excursion;
2. the capacity-scaled / relative `ΔI_required` model;
3. hardware measurement/noise floor from real RD6018/HA captures;
4. containment headroom above the finish delta;
5. CV->CC / current-ceiling-reached semantics;
6. persistence/restart behavior for the current ratchet;
7. safe OCP/current write ordering and readback;
8. fault-injection proof that network/control loss cannot restore a larger current ceiling.

Until those gates are calibrated and tested, this is an accepted architecture/safety decision, not production actuator behavior.

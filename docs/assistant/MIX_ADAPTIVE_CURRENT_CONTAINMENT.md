# Mix Adaptive Current Containment

Status: **ACCEPTED / SOFTWARE RATCHET IMPLEMENTED / ACTUATOR AUTHORITY CALIBRATION-GATED**

This note records the accepted safety mechanism for V2 Mix. The non-actuating ratchet/persistence machinery now exists in `mix_current_containment.py`; no production headroom, measurement-floor or current-write authority has been enabled because those values still require real RD6018/battery characterization.

## Purpose

During a high-voltage Mix stage, once the battery has demonstrated a confirmed lower current minimum, the hardware current ceiling should eventually be tightened dynamically. The purpose is to reduce the amount of current/power the battery can suddenly accept if the remote control path (bot / HA / network) becomes unavailable while the RD6018 remains energized.

This is a containment layer, not a chemistry-completion criterion and not a replacement for verified Output OFF, the edge safety lease/watchdog, thermal limits, or ordinary electrical protections.

## Core invariant

Adaptive containment may only remove current authority. It must never add authority.

For one Mix session:

```text
0 < I_adaptive <= I_programmed <= I_recipe
I_adaptive(t+1) <= I_adaptive(t)
```

The implemented software ratchet uses the accepted form:

```text
I_adaptive_new = min(
    I_programmed_current_ceiling,
    I_adaptive_previous,
    Imin_confirmed + containment_headroom
)
```

`containment_headroom` has **no default**. `MixContainmentPolicy()` is therefore calibration-gated and returns no actuator authority until an explicit positive calibrated headroom is supplied. Supplying a later larger programmed current can never enlarge the persisted per-session ceiling.

`containment_headroom` must eventually be larger than the Mix finish/reversal delta by a calibrated margin so that containment does not clip the very `Imin -> ΔI` signal the controller is trying to observe.

## Scale with battery capacity

Chemistry/evidence thresholds must not be defined as one universal absolute ampere value. A 1 A Mix current means ~0.014C for a 72 Ah battery but ~0.11C for a 9 Ah battery.

Therefore the future calibrated reversal/headroom model must distinguish:

- battery-scale evidence, expressed primarily in C-rate and/or relative change from `Imin`;
- hardware measurement resolution/noise, which is inherently an absolute-current floor;
- the recipe/program current ceiling, which remains independent authority and can only be tightened by containment.

A calibrated evidence model may be based on:

```text
ΔI_required = max(
    hardware_measurement_floor,
    capacity_scaled_delta,
    relative_delta_from_Imin
)
```

No production constants are selected by the current implementation; Q005/Q014 physical characterization remains responsible for real thresholds/noise/settling.

## Implemented ratchet semantics

`MixCurrentContainment` now provides a durable session-bound monotonic ceiling:

- `begin(session_id, programmed_ceiling_a)` freezes the initial programmed upper authority;
- `tighten(...)` can only keep or reduce that ceiling;
- a later larger programmed value cannot reopen authority;
- the tighter ceiling survives reconstruction/restart;
- a persisted record whose ceiling exceeds its recorded initial authority is rejected as corrupt/unsafe;
- invalid/zero/non-finite calibrated headroom is rejected;
- without calibrated headroom the decision explicitly reports `calibration_required` and `actuator_authority=False`.

This is deliberately **not yet wired to RD6018 set-current/OCP writes**. The repository now has the state machine and persistence needed to prove monotonicity before physical calibration grants actuator authority.

## Current-ceiling reach is censored evidence

If the battery current rises until the RD6018 reaches the adaptive current ceiling, the controller can no longer observe the unconstrained current rise. The supply may transition from CV to CC and reduce actual voltage below the Mix target.

The software mechanism therefore has an explicit `mark_current_ceiling_reached()` state. It does not invent a numerical tolerance for deciding that event; the caller must provide that conclusion after calibrated measurement semantics exist.

```text
CURRENT_CEILING_REACHED
```

must **not** be interpreted as `current stopped rising`, `flat current`, or failure to confirm reversal. It means only that battery acceptance reached at least the allowed ceiling.

## Protection sequencing

When actuator integration is eventually enabled, OCP/readback sequencing must preserve the existing actuator-safety rules. The software must not create an OCP value so close to the current setpoint that normal noise causes nuisance trips, and it must not weaken any existing protection.

All current/setpoint changes remain subject to configured-value readback and the established protected-write ordering.

## Intended network-loss containment model

After calibration and actuator integration, the intended layered behavior remains:

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

Thermal and hard electrical safety remain independent layers. Adaptive current containment reduces the immediate consequence of a lost control plane; it never authorizes indefinite high-voltage operation at the reduced current.

## Software tests now available

Regression coverage proves without hardware that:

1. the default uncalibrated policy has no actuator authority;
2. a calibrated ratchet can only reduce current authority;
3. the programmed ceiling remains an independent hard upper bound;
4. a tighter ceiling survives restart;
5. corrupt persistence that enlarges authority is rejected;
6. ceiling-limited evidence is represented explicitly;
7. invalid calibration values are rejected.

## Remaining physical implementation gate

Before wiring the ratchet to RD6018 actuator writes, establish on the real bench:

1. what constitutes a **confirmed** new `Imin` rather than a local excursion;
2. the capacity-scaled / relative `ΔI_required` model;
3. hardware measurement/noise floor from real RD6018/HA captures;
4. containment headroom above the finish delta;
5. CV->CC / current-ceiling-reached semantics;
6. safe OCP/current write ordering and readback under the tighter ceiling;
7. fault-injection proof that network/control loss cannot restore a larger current ceiling.

Until those gates are calibrated and tested, the durable ratchet is implemented software infrastructure, not production current-write authority.
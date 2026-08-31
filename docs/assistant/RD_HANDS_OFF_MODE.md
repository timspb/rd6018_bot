# RD6018 HANDS_OFF control mode

Status: **D060 implemented on `refactor/pb-recovery-controller-v2`; D061-D063 accepted design only.**

## Why this mode exists

RD6018 is a general-purpose programmable power supply first. Pb charging is only one use of it. Therefore Pb-specific assumptions must not own an RD6018 that the operator deliberately uses for another task.

The operator-facing switch is:

```text
🔓 Режим РД — не лезь
```

The durable runtime states are:

```text
PB_MANAGED
HANDS_OFF
```

`PB_MANAGED` is the existing V2 charging authority. `HANDS_OFF` explicitly removes bot actuator/Pb authority and leaves the physical RD6018 to the operator.

## D060 contract — general-purpose PSU / HANDS_OFF

In `HANDS_OFF`:

- `Output ON` by itself is not an orphan/fault condition;
- the bot does not apply Pb voltage/current envelopes to the live PSU state;
- `temp_ext` is not required and stale/missing battery-temperature telemetry does not cause bot shutdown;
- Pb OVP/OCP geometry is not imposed on an externally programmed PSU state;
- external-temperature integrity, chemistry transitions, Delta, Pb timers and managed edge-lease renewal do not control the output;
- normal bot writes for Output, voltage, current, OVP and OCP are rejected **without issuing a compensating OFF**;
- telemetry remains readable through the raw HA/RD boundary;
- the mode is persisted and survives a normal process restart;
- intrinsic RD6018 hardware protections are not disabled by this software mode.

This means a state such as:

```text
Output ON
set_voltage = 18.2 V
temp_ext = unavailable
OVP below the V2 Pb protection-margin rule
```

may remain observable in `HANDS_OFF` without the Pb controller changing or shutting down the supply.

### Entering HANDS_OFF

`🔓 Режим РД — не лезь` is an explicit operator release of bot ownership. It may be used from idle or while a managed AUTO/Manual program is running.

A previous unconfirmed managed `Output OFF` containment cannot be bypassed by this switch. If `_off_unconfirmed` is set, entry is rejected until physical OFF is proved.

For an active managed program the production transition is:

1. durably record `HANDS_OFF`;
2. positively disarm the edge safety lease while the managed software session is still intact;
3. switch the in-process actuator boundary to `HANDS_OFF`, so every normal bot actuator write is blocked;
4. retire the AUTO or Manual software session, timers and Delta/evidence runner **without calling a physical stop path**.

If edge-lease disarm is not positively confirmed, the durable mode is rolled back to `PB_MANAGED` and the managed session remains active.

For AUTO Mix, the durable automatic-Mix clock is terminalized with `RELEASED_TO_RD_HANDS_OFF` before the controller session is retired. This prevents an old automatic-HV authority record from being mistaken for continuing chemistry authority.

Entering `HANDS_OFF` does not change current V/I/OVP/OCP/Output. It is an ownership transfer, not a shutdown command.

### Explicit Output OFF

Normal bot `turn_off()` is blocked in `HANDS_OFF`, just like other bot actuator writes. The Telegram panel exposes a separate explicit operator action:

```text
⏹ Output OFF
```

That action goes directly to the captured raw RD/HA Output method and succeeds only after raw switch readback confirms OFF. It does **not** return Pb authority; `HANDS_OFF` remains active.

### Returning Pb control

`🔒 Вернуть контроль заряда` is accepted only with raw `Output OFF` confirmed. The transition does not alter setpoints and does not energize the output.

Live `HANDS_OFF -> PB_MANAGED` adoption while Output is already ON belongs to D061-D063 and is not implemented by D060.

## D061 — Pb adoption is an explicit authority transfer

Status: **accepted design / not implemented yet.**

A future live-adoption flow may take an already-running operator program into Pb supervision only after explicit operator authorization. Until that transaction succeeds, preflight failure must leave the external Output and settings untouched.

## D062 — adopted Mix is neither Manual nor Auto Mix

Status: **accepted design / not implemented yet.**

Adopted Mix will be a separate managed authority. Its Delta evidence epoch starts fresh at adoption; known/declared prior active time contributes to the chemistry hard maximum. Normal adopted-Mix Delta + hold ends in verified Output OFF rather than silently continuing into AUTO SAFE_WAIT/Storage. Hard Mix timeout remains abnormal `MIX_TIMEOUT -> OFF + diagnose`.

## D063 — unknown prior Mix age cannot receive a fresh autonomous budget

Status: **accepted design / not implemented yet.**

If an already-running external Mix was not observed from its OFF->ON edge and the operator cannot provide prior elapsed time, the bot must not grant a new full Ca/EFB/AGM Mix authority window. The operator must instead provide elapsed time or select a non-autonomous alternative (Manual / bounded safety-only observation / OFF as eventually implemented).

## Implementation boundary

`rd_control_mode.py` is installed after V2 safety/guardrail/UI composition so its actuator block is the outer bot-ownership boundary. `rd_hands_off_release.py` adds the explicit software-only release transaction for an already-running managed session. Neither modifies `bot_legacy.py`, and neither weakens the safety contract while authority remains `PB_MANAGED`.

No physical RD6018/ESPHome validation is claimed by this document. Hardware validation remains separate from software/CI validation.

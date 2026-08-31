# RD6018 HANDS_OFF control mode

Status: **D060 implemented in software on `refactor/pb-recovery-controller-v2`; exact ESPHome compile/flash/bench validation pending. D061-D063 are accepted design only.**

## Why this mode exists

RD6018 is a general-purpose programmable power supply first. Pb charging is only one use of it. Pb-specific assumptions therefore must not own an RD6018 that the operator deliberately uses for another task.

The operator-facing switch is:

```text
🔓 Режим РД — не лезь
```

The durable runtime states are:

```text
PB_MANAGED
HANDS_OFF
```

`PB_MANAGED` is the V2 charging authority. `HANDS_OFF` explicitly removes bot actuator/Pb authority and leaves the physical RD6018 to the operator.

## D060 contract — general-purpose PSU / HANDS_OFF

In `HANDS_OFF`:

- `Output ON` by itself is not an orphan/fault condition;
- the bot does not apply Pb voltage/current envelopes to the live PSU state;
- `temp_ext` is not required and stale/missing battery-temperature telemetry does not cause Pb shutdown;
- Pb OVP/OCP geometry is not imposed on an externally programmed PSU state;
- external-temperature integrity, chemistry transitions, Delta, Pb timers and managed edge-lease renewal do not control the output;
- normal bot writes for Output, voltage, current, OVP and OCP are rejected **without issuing a compensating OFF**;
- telemetry remains readable through the raw HA/RD boundary;
- the mode is persisted and survives a normal process restart;
- intrinsic RD6018 hardware protections are not disabled by this software mode;
- stale pre-HANDS_OFF AUTO restore authority is not allowed to revive later when Pb control returns.

A state such as:

```text
Output ON
set_voltage = 18.2 V
temp_ext = unavailable
OVP below the V2 Pb protection-margin rule
```

may remain observable in `HANDS_OFF` without the Pb controller changing or shutting down the supply.

## Entering HANDS_OFF while idle / Output OFF

For an idle managed controller the transition uses the ordinary verified-OFF edge disarm path when the edge lease is enforced. This preserves the existing rule that ordinary lease disarm may not clear a managed safety lease while RD6018 Output is still ON.

A previous unconfirmed managed `Output OFF` containment cannot be bypassed. If `_off_unconfirmed` is set, entry is rejected until physical OFF is proved.

The mode write is durable before ordinary in-process HANDS_OFF becomes authoritative.

## Releasing an active managed AUTO/Manual session

This path is intentionally different from idle HANDS_OFF entry because the operator explicitly asks to preserve the currently running Output and setpoints.

### Two-step, session-bound confirmation

When AUTO or Manual is active, `🔓 Режим РД — не лезь` is **not** itself the destructive action. The UI opens a second screen explaining that charge automation, Delta/timers and managed lease ownership will be released while Output and V/I/OVP/OCP remain unchanged.

Only:

```text
🔓 ОТПУСТИТЬ РД
```

executes the transfer. `Отмена` is non-actuating.

The confirmation is bound to the exact active session identity. If the original session ends or a replacement session starts before Execute is pressed, that old confirmation is rejected. Old Telegram dashboard messages that still contain the historical `rd_hands_off_enable` callback are dynamically routed into the confirmation flow when a managed session is active; they cannot bypass it.

### Why ordinary edge `disarm()` is not used

The ESPHome normal disarm contract is deliberately OFF-only:

```text
fresh direct Modbus
+ fresh direct Output register 18
+ Output OFF
        -> normal disarm allowed
```

Using that operation for an active Output-preserving ownership transfer is impossible by design and previously constituted a cross-layer contract bug.

Active release instead uses a dedicated edge command:

```text
Safety Lease Release To Hands Off
```

It may execute only from an already-armed, healthy managed lease with fresh direct RD6018/Output readback and with neither trip nor boot quarantine active. It does **not** write Output register 18 and does **not** clear a trip/quarantine.

Successful edge release:

```text
managed_session = false
last_renew = 0
generation++
Output unchanged
```

Python accepts success only after positive readback proves:

- the edge lease is no longer armed;
- generation changed from the prepared managed state;
- trip/quarantine remain clear;
- direct Modbus is still fresh;
- remaining managed lease time is effectively zero.

### Renewal-race containment

Lease renewal and ownership release are serialized. Before waiting for an in-flight heartbeat, the release path synchronously suspends future renewals. A provisional in-process HANDS_OFF barrier then blocks new starts and bot setpoint/Output-ON writes and routes reads through the raw boundary while the edge transfer is being prepared.

This prevents the prior race:

```text
release starts
     |
     +-- background get_all_live renews lease
     |
edge gets disarmed/released
     |
late renewal re-arms watchdog
```

from occurring after operator release.

### Commit and failure semantics

The release sequence is divided around the durable ownership commit.

Before durable HANDS_OFF:

```text
fresh exact-session confirmation
-> suspend/serialize renewals
-> verify dedicated edge release API + healthy armed state
-> write durable HANDS_OFF
```

If preparation fails before the durable mode write, in-process authority returns to `PB_MANAGED`, renewal permission is restored, and the managed session remains intact.

After durable HANDS_OFF is committed:

```text
-> send dedicated edge release
-> require positive ACK
-> retire Manual/AUTO software authority without physical stop
-> clear stale AUTO restore state
```

A lost/ambiguous edge acknowledgement **after** the durable commit does not roll software back to `PB_MANAGED`. The command may already have reached ESPHome; rolling back would risk managed software operating without the local dead-man it assumes. The conservative result is therefore:

```text
HANDS_OFF remains durable
bot actuators remain blocked
software charge authority is retired
operator gets a containment warning
edge watchdog may still turn Output OFF if release did not actually complete
```

That uncertainty must be resolved from edge telemetry/operator inspection, not by silently reacquiring Pb authority.

### AUTO Mix accounting

For AUTO Mix, the durable automatic-Mix clock is terminalized as:

```text
RELEASED_TO_RD_HANDS_OFF
```

before controller retirement where possible. This prevents old automatic-HV time authority from being mistaken for a continuing chemistry session. HANDS_OFF remains the outer actuator boundary even if diagnostic/accounting cleanup itself fails.

### Manual accounting

Manual runner/timers/evidence are retired without calling `ManualSessionManager.stop()`, because ordinary Manual stop owns a physical Output OFF. State becomes `STOPPED` with `released_to_rd_hands_off`; the old runner must no longer be active.

## Explicit Output OFF in HANDS_OFF

Normal bot `turn_off()` is blocked in `HANDS_OFF`, like other bot actuator writes. Telegram exposes a separate explicit operator action:

```text
⏹ Output OFF
```

That action goes to the captured raw RD/HA Output method and succeeds only after raw switch readback confirms OFF. It does **not** return Pb authority; HANDS_OFF remains active.

## Returning Pb control

`🔒 Вернуть контроль заряда` is accepted only when:

- no stale managed AUTO/Manual software authority is active;
- raw RD Output is positively confirmed OFF.

The transition does not alter setpoints and does not energize the output. Any stale AUTO restore/session file from before HANDS_OFF is cleared, so returning Pb authority requires a fresh operator start rather than silently resuming the old charge.

Live `HANDS_OFF -> PB_MANAGED` adoption while Output is already ON belongs to D061-D063 and is not implemented by D060.

## D061 — Pb adoption is an explicit authority transfer

Status: **accepted design / not implemented yet.**

A future live-adoption flow may take an already-running operator program into Pb supervision only after explicit operator authorization. Until that transaction succeeds, preflight failure must leave the external Output and settings untouched.

## D062 — adopted Mix is neither Manual nor Auto Mix

Status: **accepted design / not implemented yet.**

Adopted Mix will be a separate managed authority. Its Delta evidence epoch starts fresh at adoption; known/declared prior active time contributes to the chemistry hard maximum. Normal adopted-Mix Delta + hold ends in verified Output OFF rather than silently continuing into AUTO SAFE_WAIT/Storage. Hard Mix timeout remains abnormal `MIX_TIMEOUT -> OFF + diagnose`.

## D063 — unknown prior Mix age cannot receive a fresh autonomous budget

Status: **accepted design / not implemented yet.**

If an already-running external Mix was not reliably observed from its OFF->ON edge and the operator cannot provide prior elapsed time, the bot must not grant a new full Ca/EFB/AGM Mix authority window. The operator must instead provide elapsed time or select a non-autonomous alternative (Manual / bounded safety-only observation / OFF as eventually implemented).

## Implementation boundary

`rd_control_mode.py` is installed after V2 safety/guardrail/UI composition so its actuator block is the outer bot-ownership boundary. `rd_hands_off_release.py` adds the active managed-session release transaction and session-bound Telegram confirmation. `edge_safety_lease.py` and `esphome/rd6018_safety_lease.yaml` jointly implement the dedicated live ownership-release handshake.

Neither D060 nor HANDS_OFF changes `bot_legacy.py` chemistry semantics. The exact ESPHome package must be compiled/flashed and the live release/renewal race/ACK-loss behavior must be bench-tested before production reliance. Green Python CI is not physical validation.

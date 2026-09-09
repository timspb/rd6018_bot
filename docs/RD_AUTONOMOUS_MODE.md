# RD Autonomous Operation Boundary

## Purpose

Separate physical RD6018 safety, bot ownership and control-plane availability.

`AUTONOMOUS` does **not** mean autonomous Pb charging. It means the RD6018 may be used as a general-purpose programmable power supply without a permanently available bot/HA/Wi-Fi control plane. The connected load may be a battery of any chemistry, electronics, a motor, a heater, a lamp, a laboratory load, or another device.

## Two independent axes

### Ownership

Who may issue application-level actuator commands:

- `PB_MANAGED`: bot owns the managed application path.
- `HANDS_OFF`: external operator/application owns the PSU; bot actuator paths are blocked.

`HANDS_OFF` is an ownership-transfer workflow. It is **not** evidence that the edge is in `AUTONOMOUS` and does not promise operation through an ESP reboot or loss of the home control plane.

### Operation mode

The ESP edge separately publishes a persistent `AUTONOMOUS` bit:

- `AUTONOMOUS=OFF`: existing managed/HANDS_OFF behavior; D056 lease semantics remain available to managed operation.
- `AUTONOMOUS=ON`: explicit generic-PSU operation independent of managed heartbeat availability.

The bot may enter or exit `AUTONOMOUS` only with fresh confirmed Output OFF. Entry first crosses the software `HANDS_OFF` ownership boundary and disarms the managed lease, then requires a positive edge ACK (mode + generation + fresh readback). Exit positively clears the edge mode while Output is still OFF and only then returns software ownership to `PB_MANAGED`. A stale historical `HANDS_OFF -> PB` callback cannot bypass the autonomous-exit transaction.

The existing live `HANDS_OFF -> managed` D061 adoption remains a separate Output-ON transaction and explicitly rejects `AUTONOMOUS`. AUTONOMOUS is never silently live-adopted.

## Proven edge-local intrinsic safety

The repository currently proves only the following additional application-agnostic ESPHome authorities (D064):

- internal RD/PSU temperature at the accepted 55 °C cutoff -> local Output OFF;
- fresh non-zero raw RD register-16 protection status (OVP/OCP/OPP/other non-zero protection code) -> local Output OFF.

These guards do not depend on Pb chemistry, charge session, `temp_ext`, battery voltage, Telegram, HA or managed lease age, and they do not rewrite V/I/OVP/OCP.

Do **not** infer a generic autonomous software ceiling from Pb values such as 16.6/17.5 V or 12 A. Separate absolute autonomous voltage/current/power limits are not yet physically validated. RD native protection behavior and any future generic local ceilings require exact-firmware bench evidence before they can be claimed as a production safety envelope.

Missing intrinsic telemetry is also not reclassified as proof of an autonomous fault. In managed operation, D056 and the existing runtime freshness rules remain fail-closed.

## Managed-only application/control-plane policy

The following must not, by themselves, terminate a valid explicit autonomous operation:

- missing home Wi-Fi / Home Assistant / Telegram;
- missing Pb charge session or controller activity;
- missing Pb chemistry profile;
- missing/stale external battery temperature sensor;
- expiration or absence of the managed control-plane lease heartbeat.

They remain relevant where the current managed Pb contract requires them.

## External temperature

`temp_ext` is application-specific, not intrinsic PSU authority:

- managed Pb charging may require it and retains its current fail-closed semantics;
- general autonomous PSU operation does not require the sensor to exist or remain connected.

A future autonomous emergency rule for an available external probe must use a separately accepted and validated threshold; this document does not invent one.

## Reboot / unknown state

- explicit non-conflicting persistent `AUTONOMOUS=ON` may survive ESP reboot without managed boot quarantine;
- managed + autonomous persistent conflict is fail-closed;
- missing/unknown edge mode is never inferred as autonomous;
- bot startup resolves explicit edge authority before any managed startup recovery is allowed to actuate; unavailable authority keeps bot actuation provisionally blocked until resolved.

## Validation gate

Repo/CI success is not physical deployment evidence. Before production use of autonomous mode, compile/flash the exact ESPHome target and bench-test at minimum:

1. autonomous reboot with Output OFF and subsequent local operation;
2. Wi-Fi/HA loss while autonomous and Output ON;
3. managed lease loss still performs the existing D056 OFF behavior;
4. local 55 °C / raw protection-code OFF behavior;
5. autonomous enter/exit ACK and power-loss/torn-transition behavior;
6. RD native voltage/current/power protection behavior before declaring generic limits.

Do not weaken managed safety to make autonomous operation work. The solution is explicit authority separation, not a bypass flag or a longer orphan timeout.

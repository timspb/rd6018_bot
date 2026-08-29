# RD6018 communication-loss failsafe

## Safety objective

A controller-managed charge must not be able to remain energized indefinitely when
control communications disappear.  This is especially important in `Mix Mode`, where
16.3--16.5 V may be intentionally held for hours and the normal software finish logic
needs live battery voltage/current/temperature evidence.

The safety design uses a **renewable dead-man lease**, not only a conventional network
watchdog.  A healthy controller must repeatedly prove liveness.  Loss of that proof
naturally converges to local `Output OFF`.

## Production contract

- Edge lease TTL: **30 minutes**.
- Bot renewal cadence: **10 minutes**.
- Renewal is armed **before every controller-managed Output ON**.
- A Home Assistant HTTP success is not sufficient acknowledgement.
- Renewal succeeds only when:
  - the ESPHome lease generation changes;
  - `Safety Lease Armed` is ON;
  - the ESPHome node reports a direct RD6018 Modbus observation no older than 20 s;
  - the reported remaining lease is effectively a freshly replenished 30-minute lease
    (production ACK allows only a small telemetry/publication slack).
- Between scheduled renewals the bot also rejects an unexpectedly short remaining lease.
- A missed/invalid renewal while communication is still available immediately requests
  and verifies RD6018 `Output OFF` through the existing actuator safety boundary.
- If the bot/HA/network is completely gone, the ESPHome node expires the lease locally
  and writes RD6018 Output OFF without depending on HA or Python.
- Once the edge lease trips it is **latched**. A late process cannot simply renew the old
  charge. The trip can be cleared only after the edge node itself has fresh Modbus and
  reads RD6018 Output OFF.
- **Every ESPHome reboot enters a boot quarantine**, whether or not a managed-session
  preference was already flushed to flash. The node repeatedly requests RD6018 Output
  OFF until direct Modbus is fresh and the locally-read Output state is OFF; no lease
  can be armed during this quarantine.
- If a managed-session preference survives the reboot, its trip remains latched after
  the boot quarantine and requires an explicit verified-OFF disarm before a new start.

The ESPHome package is `esphome/rd6018_safety_lease.yaml`.

`RD6018_EDGE_LEASE_REQUIRED=1` is the production default. Setting it to `0` is an
explicit emergency rollback that removes this independent communication-loss boundary;
it must not be treated as the normal operating configuration.

## Failure-domain matrix

| Failure | Existing bot watchdog | Edge lease | Residual risk |
|---|---|---|---|
| Python bot crashes | Cannot act | OFF within 30 min | bounded |
| HA process stops | Cannot act | OFF within 30 min | bounded |
| Wi-Fi / HA API path dies | Cannot act | ESPHome timer continues locally; OFF within 30 min | bounded if ESPHome<->RD Modbus remains usable |
| HA returns stale cached numeric states | Can be fooled | generation + near-full remaining + direct-Modbus ACK prevents false renewal; local TTL still expires | bounded |
| Bot alive but lease renewal fails | Immediate verified OFF | lease remains fail-safe | bounded |
| ESPHome reboots mid-charge | Bot may temporarily lose HA | unconditional boot quarantine repeatedly forces local OFF; persisted managed session additionally latches trip | bounded if ESPHome<->RD Modbus becomes usable |
| ESPHome loses power and stays down while RD6018 stays powered | Cannot act | Edge CPU is absent | **needs RD-internal timer** |
| ESPHome<->RD6018 UART/Modbus dies | Cannot command RD through HA | lease latches and retries OFF as soon as Modbus returns | **RD may remain ON while UART is physically unavailable** |
| RD6018 firmware itself hangs with output ON | No reliable command path | No reliable command path | requires an RD-internal independent mechanism |
| External battery temperature telemetry disappears | Runtime fail-close/verified OFF if command path exists | lease remains armed until OFF | bounded if Modbus usable |

The remaining hard failure domain is therefore **loss of the ESPHome-to-RD6018 control
path while RD6018 itself continues sourcing power** (including a dead/unpowered ESPHome
controller). The correct next layer is the RD6018 firmware's own output timer, if it can
be safely controlled and positively verified over a documented register interface.

## Native RD6018 Timer Off -- intended third layer

UniSoft firmware documents a Current Session timer:

- `Timer Mode = Single`;
- `Timer Off` defines the output-on time limit and turns Output OFF at expiry;
- `Timer On = 00:00:00` leaves the output off after expiry;
- timer accounting is anchored to when RD6018 Output was enabled;
- if Output is already ON and timer settings are changed with `Timer Reset = OFF`, the
  elapsed ON time is **not** reset. The new Timer Off value behaves like an absolute
  cutoff for the current ON session;
- `Timer Reset = ON` is the documented mechanism that resets/restarts timer timing when
  the settings are applied while Output is already ON.

This distinction is critical. Example: if the current Output-on elapsed time is 13:20
and `Timer Off` is changed to 14:00 with `Timer Reset = OFF`, only about 00:40 remains.
It is **not** a fresh 14-hour countdown. Likewise, repeatedly writing `Timer Off = 00:30`
while a session has already been ON for longer than 30 minutes would not implement a
rolling 30-minute lease unless the timer is explicitly reset at each refresh.

The UniSoft documentation gives an even stronger example: if Output has already been ON
for more than one minute, then a one-minute Timer Off is applied without resetting the
timer origin, Output may turn OFF immediately because that minute has already elapsed.
Enabling Timer Reset forces the timer to begin again when the settings are applied.

Therefore the proposed RD-internal dead-man design must not merely "rewrite Timer Off
periodically". It must either:

1. positively control and verify `Timer Reset` together with each refresh, proving on the
   physical unit that the update is atomic and does not glitch Output; or
2. use a different pre-armed deadline strategy that never requires mutating Timer Mode
   while Output is already ON.

The first option would provide the desired rolling lease semantics, e.g. a 30-minute
native cutoff refreshed every 10 minutes. The second is safer if live reset semantics
cannot be proven.

However, the public standard RD60xx Modbus maps used by the current ESPHome integration
expose the normal operating registers (V/I, Output, OVP/OCP, battery telemetry, etc.) but
do not identify safe remote register addresses for the UniSoft Current Session timer.
The UniSoft manual also explicitly warns that changing Timer Mode settings while Output
is ON can have unexpected behavior.

Therefore the bot must **not guess or brute-force timer registers on an energized PSU**.
Native timer support stays disabled until the addresses and semantics are established on
the physical unit.

## Bench procedure for native timer discovery

Use a dummy load / non-battery load and keep Output OFF during register discovery.

1. Dump the readable holding-register range with Timer Mode OFF.
2. Change only one panel setting (`Timer Off`, then `Timer Mode`, then `Timer Reset`).
3. Dump the same register range after each change.
4. Diff values and identify candidate addresses.
5. Reboot and repeat to distinguish volatile Current Session state from unrelated RTC
   or display values.
6. Read candidate registers repeatedly without writes.
7. With Output OFF, write only a confirmed candidate and verify the panel/readback.
8. With a current-limited dummy load, prove a short timer (for example 60 s) turns
   Output OFF without any ESPHome/HA traffic.
9. Prove the elapsed-session rule explicitly: turn Output ON, wait e.g. 90 s, apply a
   120 s Timer Off with Timer Reset OFF, and verify that only about 30 s remains.
10. Then repeat with Timer Reset ON and verify that a fresh full 120 s begins when the
    settings are applied.
11. Verify whether the required Timer Off/Timer Reset refresh can be written and read
    back atomically while Output remains ON, without a transient OFF/ON or mode glitch.
12. Only after these tests add the native timer as another mandatory lease backend.

## Why the edge lease applies to all managed charging

Mix is the highest-consequence case, but making the dead-man timer stage-specific creates
an unnecessary hole during Main/Desulf transitions and restart/restore. The edge lease
therefore protects **every controller-managed Output ON**. Mix receives the same 30-minute
maximum communication-loss exposure, while ordinary stages gain the same fail-safe for
free.

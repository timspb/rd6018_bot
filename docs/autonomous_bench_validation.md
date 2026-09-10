# AUTONOMOUS bench validation plan

Use [`autonomous_hardware_failure_capture.md`](autonomous_hardware_failure_capture.md)
for any failed or ambiguous hardware result.

Status: software boundary implemented; exact-node physical validation required before production reliance.

This plan validates the already-implemented `AUTONOMOUS` edge operation mode. It
does not authorize autonomous Pb charging, change safety thresholds, or replace
the managed lease contract.

## Preconditions

- Record the exact ESPHome firmware version and build hash.
- Connect the exact RD6018 node and the intended load.
- Confirm an emergency physical disconnect is immediately available.
- Record initial Output, V/I/OVP/OCP, protection and edge authority state.
- Begin with Output OFF and no active managed Pb session.
- Capture timestamps and positive acknowledgements for every transition.

## Four-dimensional state model

Every observation records all four dimensions; mode and Output alone are not
enough to determine the correct response.

| Dimension | Values | Meaning |
|---|---|---|
| Operation mode | `PB_MANAGED`, `HANDS_OFF`, `AUTONOMOUS` | How the RD is operated; `HANDS_OFF` is ownership transfer, not autonomous operation. |
| Output state | `OFF`, `ON` | Current physical Output readback. |
| Ownership provenance | `BOT_MANAGED`, `FOREIGN`, `AUTONOMOUS`, `UNKNOWN` | Who started or currently owns an ON Output, with `UNKNOWN` used when evidence is insufficient. |
| Control plane | `ONLINE`, `OFFLINE`, `RECOVERING` | Availability of Wi-Fi/HA/Telegram and recovery progress; this does not by itself establish ownership. |

`BOT_MANAGED` requires evidence such as a bot-started Output, a restored
managed session or an active charge session. `FOREIGN` covers manual or
external-controller activation. `AUTONOMOUS` is edge-owned operation. Never
infer ownership from voltage/current, Wi-Fi loss or an unarmed lease alone.

## Wi-Fi-loss ownership matrix

| Mode | Ownership provenance | Output | Control plane event | Required behavior |
|---|---|---|---|---|
| `PB_MANAGED` | `BOT_MANAGED` | `ON` | Wi-Fi loss | Existing managed fail-closed behavior. |
| `PB_MANAGED` | `FOREIGN` | `ON` | Wi-Fi loss | Do not classify it as a bot-owned charge; use the explicit ownership-decision flow, with no automatic adoption or takeover. |
| `AUTONOMOUS` | `AUTONOMOUS` | `ON` | Wi-Fi loss | Continue edge-owned operation; no bot shutdown solely for control-plane loss. |
| Any mode | Any provenance | `OFF` | Wi-Fi loss | No emergency action solely because Wi-Fi disappeared. |
| `AUTONOMOUS` | `AUTONOMOUS` | `ON` or `OFF` | Wi-Fi recovery | Monitoring may resume, but ownership and mode do not change; issue no actuator command and perform no automatic takeover. |

## Tests

### A01 — Enter AUTONOMOUS

Procedure:

1. Confirm the preconditions and record the initial edge mode, generation and Output readback.
2. Request the existing explicit AUTONOMOUS transition as an operator action.
3. Confirm the edge command acknowledgement, mode readback and generation advance.
4. Reboot or reread the edge state as permitted by the test setup and confirm persistence.
5. Attempt only safe, non-actuating bot control probes and record that they are rejected.

- require fresh confirmed Output OFF;
- verify positive edge mode/generation/readback acknowledgement;
- verify the autonomous state is persistent;
- verify bot Output/V/I/OVP/OCP writes, Pb start and session restore are blocked.

Expected: explicit acknowledgement, durable state, and no bot control authority.

### A02 — Wi-Fi loss and ownership provenance

Procedure:

Run the following subcases independently, recording mode, Output,
ownership provenance and control-plane state before and after each case.

#### A02.1 — Output OFF

1. Confirm Output OFF in the selected mode.
2. Disconnect Wi-Fi and observe without changing the RD or issuing bot commands.
3. Restore Wi-Fi and record any transition.

Expected: no emergency action solely because Wi-Fi disappeared.

#### A02.2 — BOT_MANAGED Output ON

1. Start a pre-approved managed operation through the existing managed path.
2. Confirm `PB_MANAGED`, `BOT_MANAGED`, Output ON and fresh lease evidence.
3. Disconnect Wi-Fi and observe the existing managed fail-closed response.

Expected: current managed behavior remains unchanged.

#### A02.3 — FOREIGN Output ON

1. Establish and record manual/external/unknown provenance without claiming bot ownership.
2. Confirm the applicable ownership-decision flow before disconnecting Wi-Fi.
3. Disconnect Wi-Fi and observe without automatic adoption or takeover.

Expected: the Output is not treated as a bot-owned Pb charge; any containment
or ownership decision follows the existing explicit contract.

#### A02.4 — AUTONOMOUS Output ON

1. Enter AUTONOMOUS with positive edge acknowledgement.
2. Apply the pre-approved safe generic program and confirm edge-owned Output ON.
3. Disconnect Wi-Fi and wait at least 30 minutes, recording local Output and protection observations.

Expected: operation continues under edge/RD control; no bot shutdown solely
from Wi-Fi loss.

#### A02.5 — Wi-Fi recovery after AUTONOMOUS

1. Restore Wi-Fi after A02.4 while preserving the autonomous mode and Output state.
2. Observe monitoring resumption and record mode, ownership, generation and Output.

Expected: monitoring may resume, but no ownership change, actuator command or
automatic takeover occurs.

Expected: subcase-specific behavior above; record the exact result for each
subcase and stop on any ownership ambiguity.

### A03 — Home Assistant unavailable

Procedure:

1. Confirm AUTONOMOUS and a safe locally controlled Output state.
2. Disable or isolate the HA/control-plane path without changing the RD program.
3. Observe for the approved test interval and record Output/protection state.
4. Restore HA and record any state transition.

Expected: no managed shutdown and no bot actuator command.

### A04 — ESP reboot

Procedure:

1. Confirm Output OFF and record persistent mode, managed-session bit and generation.
2. Reboot the ESP only; do not restart or reconfigure the bot.
3. Wait for the edge to publish its post-boot state and record quarantine/trip indicators.
4. Confirm AUTONOMOUS persistence and deterministic Output behavior.
5. Repeat under an approved safe load test only if A01–A03 passed.

Expected: autonomous state resolution is deterministic; no accidental managed
lease quarantine or surprise bot resume occurs.

### A05 — Local safety

Procedure:

1. Confirm AUTONOMOUS, the approved safe generic program, emergency disconnect and local readbacks.
2. Validate internal PSU thermal protection and RD hardware protection using only approved non-destructive stimuli.
3. Record local protection indication, Output state and recovery behavior.
4. Stop on any ambiguous or unexpected electrical state.

Expected: intrinsic edge/RD protection remains active in AUTONOMOUS. Do not
infer generic voltage/current/power limits from Pb recipe limits or perform unsafe electrical tests.

### A06 — Return to MANAGED

Procedure:

1. Confirm Output OFF and fresh canonical readback.
2. Request explicit autonomous exit.
3. Verify the edge acknowledgement and generation transition.
4. Verify software returns to `PB_MANAGED` only after the OFF-only boundary.
5. Verify no old Pb session or setpoints are silently resumed.

Expected: explicit acknowledgement, no surprise Output ON, and a fresh managed
start required.

### A07 — Relocation scenario

Procedure:

1. Confirm A01 passed, the safe generic program is recorded and the emergency disconnect is ready.
2. Capture home-side mode/generation and Output evidence.
3. Move the device without the original Wi-Fi, HA or Telegram.
4. Use only local RD controls and do not attempt host recovery.

Expected: operation continues under explicit edge/RD protection without the home
control plane. Use the emergency disconnect and complete a failure report if
authority becomes ambiguous.

### Transport sub-check — Telegram unavailable

1. Confirm AUTONOMOUS and a safe locally controlled Output state.
2. Block Telegram transport only; do not alter HA, firmware or RD controls.
3. Observe for the approved interval and record Output/protection state.
4. Restore Telegram and record any state transition.

Expected: no Telegram-caused shutdown or bot actuator command.

## Evidence and stop conditions

Record firmware version, node identity, timestamps, raw readbacks, edge mode and
generation, Output state, protection state and recovery result. Stop immediately
on ambiguous authority, missing acknowledgement, unexpected Output change or
uncertain protection behavior. Restore Output OFF at the end unless the approved
 test explicitly requires otherwise.

## Evidence gate by test

For every case, missing evidence is a failed gate, not an inferred pass.

### A01 — Enter AUTONOMOUS

Before: expect Output OFF and no managed session; record mode, ownership, generation, edge lease/trip state and required operator confirmation.

During: observe explicit operator action, edge mode/generation ACK, persistence and rejected bot actuator probes. Do not change setpoints or start/restore Pb charging.

After: PASS requires persistent AUTONOMOUS plus rejected bot control. FAIL on missing ACK, accepted actuator command or unexpected Output change. Keep Output OFF and follow rollback.

### A02 — Wi-Fi loss

Before: execute A02.1–A02.5 independently. For every subcase record expected mode, Output, ownership provenance, control-plane state, local Output/protection readbacks and host health logs.

During: disconnect Wi-Fi only for the selected subcase; for A02.4 wait at least 30 minutes. Observe locally without changing the RD program or using bot commands. For A02.5 restore Wi-Fi only after the autonomous observation interval.

After: A02.1 passes with no action solely from Wi-Fi loss; A02.2 preserves existing managed fail-close behavior; A02.3 does not auto-adopt or classify foreign Output as bot-owned; A02.4 has no autonomous shutdown; A02.5 resumes monitoring without ownership change or actuator command. Any mismatch, automatic takeover or ambiguity is FAIL: restore connectivity, preserve evidence and stop.

### A03 — Home Assistant unavailable

Before: expect confirmed AUTONOMOUS and a safe local program; record HA, edge, Output and protection state.

During: isolate HA/control plane for the approved interval; do not alter firmware, RD controls or setpoints.

After: PASS means RD remains locally operating. FAIL means HA absence alone changes autonomous Output. Restore HA and stop on ambiguity.

### A04 — ESP reboot

Before: expect Output OFF; record persistent mode, managed-session bit, generation, quarantine/trip and local readback.

During: reboot only the ESP and observe boot authority publication. Do not restart the bot or alter the RD program.

After: PASS means deterministic autonomous persistence without managed recovery or surprise enable. FAIL means unknown state, lost authority or managed actuation. Keep Output OFF and roll back.

### A05 — Local safety

Before: expect AUTONOMOUS with the approved safe generic program, Output/protection readbacks and emergency disconnect ready.

During: verify internal thermal and RD hardware protection with approved non-destructive stimuli. Do not perform unsafe electrical tests or defeat protection.

After: PASS means intrinsic protection remains active and produces the documented safe result. FAIL on missing protection, ambiguous state or unexpected Output behavior. Use the emergency disconnect, preserve evidence and stop.

### A06 — Return to MANAGED

Before: expect AUTONOMOUS with fresh canonical Output OFF evidence; record mode/generation and edge state.

During: request explicit exit and observe edge ACK/generation advance, then PB_MANAGED. Do not use stale historical callbacks.

After: PASS requires `AUTONOMOUS -> Output OFF -> edge ACK -> PB_MANAGED` and no old-session resume. FAIL if PB_MANAGED is reached while Output is ON. Preserve evidence and stop.

### A07 — Relocation scenario

Before: expect A01 passed, safe generic program recorded and emergency disconnect ready; capture home-side mode/generation and Output evidence.

During: move the device without original Wi-Fi, HA or Telegram. Use only local RD controls and do not attempt host recovery.

After: PASS means operation continues under explicit edge/RD protection. FAIL means control-plane absence stops operation or authority becomes ambiguous. Use the emergency disconnect if needed and complete a failure report.

## Rollback procedure

If any case fails:

1. Stop the campaign; do not continue testing.
2. Disable autonomous authority through the existing explicit edge procedure.
3. Return to `PB_MANAGED` only after Output OFF is positively verified and edge acknowledgement is received.
4. Preserve logs, telemetry, timestamps, readbacks and the failure report.
5. Do not use a timeout increase, `HANDS_OFF` inference or safety bypass.

## Hardware acceptance matrix

| Test | Software layer | Firmware layer | Physical result | Status |
|---|---|---|---|---|
| A01 Enter AUTONOMOUS | Explicit transition and bot actuator block | Persistent mode, generation and ACK | Output OFF boundary confirmed | `____` |
| A02 Wi-Fi loss | Host watchdog/orphan paths inactive | Autonomous edge operation | No shutdown after >=30 min solely from Wi-Fi loss | `____` |
| A03 HA loss | Managed HA paths inactive | Autonomous edge operation | RD remains locally operating | `____` |
| A04 ESP reboot | Startup waits for authority | Persistent autonomous boot | Deterministic state, no surprise enable | `____` |
| A05 Local safety | No safety bypass in bot | Intrinsic thermal/hardware protection | Safe protection response | `____` |
| A06 Return Managed | Explicit OFF-only exit | Positive exit ACK/generation | PB_MANAGED only after verified OFF | `____` |
| A07 Relocation | No host recovery dependency | Local autonomous/intrinsic safety | Independent of home infrastructure | `____` |

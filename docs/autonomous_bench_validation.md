# AUTONOMOUS bench validation plan

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

### A02 — Wi-Fi loss

Procedure:

1. Enter AUTONOMOUS and confirm the positive edge acknowledgement.
2. Apply a pre-approved safe generic PSU program and enable Output locally.
3. Disconnect Wi-Fi while leaving the RD controls and load unchanged.
4. Wait at least 30 minutes, recording periodic local Output/protection observations.
5. Restore Wi-Fi and record whether any transition occurred.

Expected: Output remains under edge/RD control; no host shutdown is caused solely
by Wi-Fi loss.

### A03 — Home Assistant unavailable

Procedure:

1. Confirm AUTONOMOUS and a safe locally controlled Output state.
2. Disable or isolate the HA/control-plane path without changing the RD program.
3. Observe for the approved test interval and record Output/protection state.
4. Restore HA and record any state transition.

Expected: no managed shutdown and no bot actuator command.

### A04 — Telegram unavailable

Procedure:

1. Confirm AUTONOMOUS and a safe locally controlled Output state.
2. Block Telegram transport only; do not alter HA, firmware or RD controls.
3. Observe for the approved test interval and record Output/protection state.
4. Restore Telegram and record any state transition.

Expected: no managed shutdown and no bot actuator command.

### A05 — ESP reboot

Procedure:

1. Confirm Output OFF and record persistent mode, managed-session bit and generation.
2. Reboot the ESP only; do not restart or reconfigure the bot.
3. Wait for the edge to publish its post-boot state and record quarantine/trip indicators.
4. Confirm AUTONOMOUS persistence and deterministic Output behavior.
5. Repeat under an approved safe load test only if A01–A04 passed.

Expected: autonomous state resolution is deterministic; no accidental managed
lease quarantine or surprise bot resume occurs.

### A06 — Return to MANAGED

Procedure:

1. Confirm Output OFF and fresh canonical readback.
2. Request explicit autonomous exit.
3. Verify the edge acknowledgement and generation transition.
4. Verify software returns to `PB_MANAGED` only after the OFF-only boundary.
5. Verify no old Pb session or setpoints are silently resumed.

Expected: explicit acknowledgement, no surprise Output ON, and a fresh managed
start required.

### A07 — Physical safety

Procedure:

1. Confirm the emergency disconnect and an operator are present.
2. Use only approved non-destructive fault stimuli and the exact flashed firmware.
3. Validate internal PSU thermal protection and RD hardware protection behavior.
4. Record the local protection indication, Output state and recovery behavior.
5. Stop on any ambiguous or unexpected electrical state.

- internal PSU thermal protection;
- RD hardware protection behavior;
- local Output-OFF behavior when intrinsic protection trips;
- behavior when the control-plane network is absent.

Expected: intrinsic edge/RD protection remains active in AUTONOMOUS. Do not
infer generic voltage/current/power limits from Pb recipe limits.

## Evidence and stop conditions

Record firmware version, node identity, timestamps, raw readbacks, edge mode and
generation, Output state, protection state and recovery result. Stop immediately
on ambiguous authority, missing acknowledgement, unexpected Output change or
uncertain protection behavior. Restore Output OFF at the end unless the approved
test explicitly requires otherwise.

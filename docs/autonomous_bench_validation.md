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

Using the existing explicit transition workflow:

- require fresh confirmed Output OFF;
- verify positive edge mode/generation/readback acknowledgement;
- verify the autonomous state is persistent;
- verify bot Output/V/I/OVP/OCP writes, Pb start and session restore are blocked.

Expected: explicit acknowledgement, durable state, and no bot control authority.

### A02 — Wi-Fi loss

With a safe generic PSU program and Output ON, remove Wi-Fi without changing the
RD controls.

Expected: Output remains under edge/RD control; no host shutdown is caused solely
by Wi-Fi loss.

### A03 — Home Assistant unavailable

Keep the edge in AUTONOMOUS and make HA unavailable.

Expected: no managed shutdown and no bot actuator command.

### A04 — Telegram unavailable

Keep the edge in AUTONOMOUS and make Telegram unavailable.

Expected: no managed shutdown and no bot actuator command.

### A05 — ESP reboot

With Output OFF first, reboot the ESP node and observe the persisted authority.
Repeat only under an explicitly approved safe load test.

Expected: autonomous state resolution is deterministic; no accidental managed
lease quarantine or surprise bot resume occurs.

### A06 — Return to MANAGED

With Output OFF and fresh confirmed readback:

- request explicit autonomous exit;
- verify positive edge acknowledgement and generation transition;
- verify software returns to `PB_MANAGED` only after the OFF-only boundary;
- verify no old Pb session or setpoints are silently resumed.

Expected: explicit acknowledgement, no surprise Output ON, and a fresh managed
start required.

### A07 — Physical safety

Under controlled, non-destructive conditions validate:

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

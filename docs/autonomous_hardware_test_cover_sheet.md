# AUTONOMOUS hardware test cover sheet

Complete before the first physical validation run.

## Device

### RD6018

- Model: `________________________________________`
- Firmware: `________________________________________`
- Serial (if available): `________________________________________`

### ESPHome

- Device name: `________________________________________`
- Firmware SHA: `________________________________________`
- Flash date (UTC): `________________________________________`

## Software

- Bot SHA: `________________________________________`
- Deployment date/time (UTC): `________________________________________`
- Operation mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS`
- Initial ownership provenance: `BOT_MANAGED / FOREIGN_OBSERVED / AUTONOMOUS / UNKNOWN`
- Initial Output: `ON / OFF / UNKNOWN`

## Safety and test setup

- Emergency disconnect available: `YES / NO`
- Emergency disconnect location: `________________________________________`
- Load type: `________________________________________`
- Expected maximum power: `________________________________________ W`
- Operator: `________________________________________`

## A01 — Enter AUTONOMOUS

Initial state must be `PB_MANAGED` with Output positively confirmed `OFF`.

1. Verify and record Output OFF.
2. Perform the existing explicit AUTONOMOUS operator action.
3. Wait for the positive edge acknowledgement.
4. Verify the persistent autonomous state.
5. Capture the read-only `OwnershipSnapshot`.

PASS requires `mode=AUTONOMOUS`, `provenance=AUTONOMOUS`,
`confidence=VERIFIED`, and no managed actuator authority. FAIL on missing ACK,
mixed authority or an unexpected Output change.

## A02 — Wi-Fi loss

### A02.1 — AUTONOMOUS, Output OFF, Wi-Fi OFF

Disconnect Wi-Fi only and observe locally. PASS requires no shutdown and no mode
change. Record timestamps, Output, ownership snapshot and logs.

### A02.2 — AUTONOMOUS, Output ON, Wi-Fi OFF

With an approved safe generic program, disconnect Wi-Fi and observe locally for
at least 30 minutes. PASS requires Output remains controlled, no bot commands,
no managed lease shutdown and no orphan shutdown solely from Wi-Fi loss. Record
timestamps, Output, ownership snapshot, ESP/RD readbacks and logs.

## A03 — Wi-Fi restore

Restore Wi-Fi without changing the RD program, Output or mode. PASS requires
monitoring returns, AUTONOMOUS remains active, ownership is unchanged, and no
automatic takeover or V/I/Output changes occur.

## Results

| Test | Expected | Observed | PASS/FAIL | Evidence |
|---|---|---|---|---|
| A01 Enter AUTONOMOUS | AUTONOMOUS + verified autonomous provenance; no managed actuator authority | | | |
| A02.1 Wi-Fi OFF, Output OFF | No shutdown or state change | | | |
| A02.2 Wi-Fi OFF, Output ON | Output continues; no bot/lease/orphan intervention | | | |
| A03 Wi-Fi restored | Monitoring returns; ownership unchanged; no takeover or actuator changes | | | |

## Evidence collection

For every test, record:

- Timestamp: `________________________________________`
- Output readback: `________________________________________`
- OwnershipSnapshot: `________________________________________`
- Telegram log: `________________________________________`
- HA state: `________________________________________`
- ESP state: `________________________________________`
- RD telemetry/protection readback: `________________________________________`
- Operator notes: `________________________________________`

Stop on any failed criterion or ambiguous state. Use the documented rollback
procedure and preserve the complete evidence set.


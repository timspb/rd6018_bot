# AUTONOMOUS hardware failure capture

Complete this form for any failed or ambiguous A01–A03 observation.

- Timestamp (UTC): `________________________________________`
- Test ID: `A01 / A02.1 / A02.2 / A03`
- Expected: `________________________________________`
- Observed: `________________________________________`
- Output state/readback: `________________________________________`
- Mode: `PB_MANAGED / HANDS_OFF / AUTONOMOUS / UNKNOWN`
- OwnershipSnapshot:

```text
mode:       ____________________
output:     ____________________
provenance: ____________________
confidence: ____________________
```

- ESP state (mode/generation/lease/trip): `________________________________________`
- RD state (V/I/protection): `________________________________________`
- Logs: `________________________________________`
- Telemetry/screenshots/readbacks: `________________________________________`
- Recovery action: `________________________________________`
- Operator: `________________________________________`
- Reviewer: `________________________________________`

Failure handling: stop the test, preserve logs and current state, do not toggle
modes repeatedly, and return to a safe state using the documented rollback
procedure. `AUTONOMOUS` is never a safety bypass and `HANDS_OFF` is not
AUTONOMOUS.


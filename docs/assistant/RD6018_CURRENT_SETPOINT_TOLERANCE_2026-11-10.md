# RD6018 current-setpoint readback tolerance — 2026-11-10

## Incident evidence

On node104, 2026-11-10, MAIN Guard requested a current-setpoint reduction to
approximately 1.23 A. The fresh ESP Native readback reported 1.25 A. The
previous 0.02 A comparison rejected the acknowledgement because binary-float
arithmetic produced a difference slightly above 0.02 A. The transaction then
entered verified-OFF containment. This was a setpoint acknowledgement mismatch,
not proof of an OVP/OCP trip.

## Canonical tolerance

rd6018_telemetry.py now owns the shared
CURRENT_SETPOINT_READBACK_TOLERANCE_A = 0.05 value for RD6018 current-setpoint register
reconciliation. The same value is used by:

- MAIN Guard commit and verified desulfation return;
- MAIN Guard pre-ON reconciliation and admission;
- canonical session persistence against the ratcheted MAIN ceiling;
- MIX committed adaptive-current-cap evidence.

This is a readback reconciliation band (±0.05 A), not permission to raise the
recipe ceiling or the adaptive current target. The guard still requires fresh,
independent Native evidence, the same session/battery/segment identity, a
committed transaction, and verified OFF/lease boundaries where applicable.

## Deliberately unchanged

The following are not setpoint-equality checks and retain their narrower or
separately defined semantics:

- measured-current-near-zero proof while Output is OFF: ±0.01 A;
- Output OFF confirmation and hardware switch-state proof;
- OVP/OCP trip decoding and protection-state checks;
- voltage, temperature, input-voltage, and lease safety limits;
- exact journal identity, revision, and monotonic-state comparisons.

Generic output programming/readback paths already use their own broader
policy tolerances and were not widened.

## Verification

Focused tests cover acceptance inside the ±0.05 A band and rejection outside
it, including MAIN Guard commit, transaction postflight, admission, and MIX
native current-cap evidence. Production node104 deployment is a separate
controlled action and is not implied by this source change.

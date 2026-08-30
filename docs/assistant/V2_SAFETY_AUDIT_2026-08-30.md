# V2 Safety Audit — 2026-08-30

This note records the second whole-runtime safety review of `refactor/pb-recovery-controller-v2`.
It is implementation/audit evidence, not a replacement for `V2_DECISION_LOG.md`.

## Scope rechecked

The review followed the production path across:

- Telegram/legacy composition and restore entrypoints;
- V2 AUTO start, Main/Recovery/Mix authority and direct Auto Mix;
- Manual authority and restart/re-authorization;
- battery diagnostics and controlled current probe;
- recipe authorization envelopes;
- configured/readback/measured RD6018 telemetry;
- Home Assistant safe-enable transaction;
- live V/I/OVP/OCP transition interlocks;
- hardware protection status including raw OPP/unknown codes;
- verified OFF behavior;
- edge safety lease / boot quarantine;
- Cooling persistence/resume semantics;
- continuous runtime source freshness and HA timestamp semantics.

## Safety defects closed by the audit

### Measured output voltage was not a mandatory live boundary

A correct Vset/readback did not itself prove physical V_OUT was safe. Production now
requires measured output voltage while Output is ON and checks it against both the
active recipe/absolute working ceiling and configured OVP.

### Measured current used protection headroom instead of the 12 A working ceiling

Runtime current is now limited by the 12 A working envelope. OCP headroom remains
protection geometry and cannot become additional permitted charge current.

### Raw OPP / unknown protection status was not uniformly fail-closed

Raw protection register status is now authoritative. OPP and unknown non-normal codes
force verified OFF instead of depending only on legacy OVP/OCP booleans.

### Post-enable telemetry exceptions could escape after physical ON

Both `SafeOutputCoordinator` and the strict runtime enable path now treat an exception
in post-enable readback as an unsafe state and attempt verified OFF before returning or
re-raising.

### An unmanaged already-ON output could still receive live setpoint writes

V/I/OVP/OCP changes while Output is ON now require managed AUTO or Manual authority.
An orphan/unmanaged output cannot be turned into an implicit Manual session by writing
new setpoints.

### Manual could lose containment authority while OFF was uncertain

Safe-enable or stop failure with unconfirmed Output OFF no longer converts Manual into
an inactive state. It remains a managed containment state until OFF is proved, so the
runtime safety boundary continues to own the live output.

### Diagnostic probe cleanup could falsely claim forced OFF

Probe restoration/cleanup no longer suppresses shutdown exceptions or reports
`output_forced_off=True` without a confirmed OFF result. Restart recovery uses the same
truthful distinction.

### SAFE_WAIT -> Cooling -> resume could emit Output ON

Legacy Cooling resume is designed for energized source stages and emits target writes +
`turn_on`. SAFE_WAIT is explicitly Output OFF. Production composition now stores a
SAFE_WAIT-specific frozen clock in the durable Cooling token and strips all enable/
program actions when returning to SAFE_WAIT. The SAFE_WAIT timer is shifted by the
Cooling duration and Output remains OFF.

### Cooling restore could default from incomplete legacy metadata

`stage=Cooling` alone is no longer continuation authority. Automatic resume requires a
complete valid `v2_cooling_pause` token with a valid source stage, source clock and
recipe-valid target; SAFE_WAIT additionally requires its frozen relaxation clock,
storage/next-stage target and next-stage identity. Missing/corrupt metadata rejects the
restore fail-closed instead of falling back to Main.

### Legacy Vin gates contradicted the accepted V2 signal semantics

`bot_legacy.py` still contains historical `MIN_INPUT_VOLTAGE` start/restore comparisons.
Production composition neutralizes those comparisons without mutating the V1 reference
file. Vin remains visible as PSU-health evidence but cannot grant or deny Pb chemistry
or restore authority.

### Generic Pb HV current envelope was broader than implemented recipes

The generic chemistry envelope is authorization, not spare headroom. Implemented Pb HV
stages use ~0.02C Recovery/Desulfation and ~0.03C Mix; therefore AGM/EFB/Ca/Flooded
generic HV authorization is capped at **0.03C** (and the global 12 A hardware working
limit). Manual/Custom remains a separate operator authority and is not narrowed by this
chemistry envelope.

### Runtime could continue on numerically valid but stale HA telemetry

Safe-enable already rejected stale source data, but the continuously running V2 guard
previously checked only value presence/ranges/envelopes. A managed session could
therefore continue if HA kept returning an old-but-numeric battery temperature/current
or measured output voltage.

Production now applies source age/skew validation on every safety-relevant runtime poll
for continuously sampled `battery_voltage`, `current`, `temp_ext`, `temp_int`, plus
measured `voltage` whenever Output is ON. Stale/missing/incoherent source metadata is a
fail-closed condition and forces verified OFF when energized.

Home Assistant `last_reported` is the preferred heartbeat timestamp because it advances
when the integration reports an entity even if its numeric value did not change.
`last_updated` remains a compatibility fallback for older/degraded adapters. This avoids
false shutdowns on a genuinely flat temperature/current value while still detecting a
sensor/integration that stopped reporting.

Static Vset/Iset/OVP/OCP timestamps are intentionally **not** treated as liveness clocks:
a valid unchanged configuration may remain unchanged for hours. Their actual values and
protection geometry are nevertheless re-read/revalidated by the runtime envelope. The
edge safety lease remains a separate direct-Modbus/output-register proof and is not
replaced by HA freshness.

## Residual physical failure domain

Software/HA/edge controls cannot guarantee shutdown if the ESPHome-to-RD6018 Modbus
path is physically unavailable while RD6018 itself remains energized and sourcing
power, or if RD6018 firmware/output hardware is itself stuck ON. The edge lease retries
OFF when Modbus returns, but a truly independent RD-internal timer remains the desired
third layer once its register addresses and live-update semantics are physically proven.
See `../RD6018_FAILSAFE.md`.

## Validation meaning

Unit CI proves deterministic software contracts only. It does not replace the physical
bench/on-battery gates in `V2_VALIDATION_PLAN.md`, especially measured V_OUT/OFF proof,
HA `last_reported` cadence for unchanged values, stale-sensor fault injection, edge
lease fault injection, Cooling restart, interrupted Manual/probe recovery and real
charge traces.

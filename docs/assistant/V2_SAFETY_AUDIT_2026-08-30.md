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
- Home Assistant bulk/fallback telemetry paths;
- live V/I/OVP/OCP transition interlocks;
- hardware protection status including raw OPP/unknown codes;
- verified OFF behavior and post-failure containment;
- edge safety lease / boot quarantine;
- Cooling persistence/resume semantics;
- continuous runtime source freshness and HA timestamp semantics;
- auxiliary RecoveryOrchestrator lifecycle and cancellation/exception cleanup.

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

### Diagnostic task cancellation could strand the reduced-current probe setpoint

`asyncio.CancelledError` is not a normal `Exception`. A live probe cancelled after the
current-reduction step could previously bypass the ordinary exception cleanup and leave
RD6018 at the diagnostic current until another watchdog/restart path intervened.

The probe executor now catches the broader cancellation boundary only for cleanup. If a
step has already occurred it shields the restore-or-OFF transaction, restores and
read-backs the original current when possible, otherwise requests verified OFF, and
then re-raises cancellation instead of converting cancellation into successful probe
evidence. Normal exceptions still return a truthful `ProbeResult` with separate
restore/OFF facts.

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
therefore continue if HA kept returning old-but-numeric physical telemetry or old status
values that still looked plausible.

Production now applies source age/skew validation on every safety-relevant runtime poll.
The heartbeat set contains continuously sampled physical channels
`battery_voltage`, `current`, `temp_ext`, `temp_int`; measured `voltage` whenever Output
is ON; Output switch state; hardware protection status; and the CV/CC regulation source
used by chemistry evidence.

For protection and regulation the guard follows the same authority preference as the
telemetry decoder: raw `protection_code` / `regulation_code` when exposed, otherwise
legacy `ovp_triggered` + `ocp_triggered` and `is_cv` + `is_cc`. This matters because a
stale `CV=true`, stale normal-protection status, or stale Output=ON/OFF value can alter
actuator/FSM decisions even when V/I/T are still fresh. Those status/evidence channels
therefore cannot be treated as timeless configuration.

Stale, missing or incoherent heartbeat metadata is fail-closed and forces verified OFF
when energized. Production V2 additionally rejects a complete absence of `_meta` while
a managed/energized safety context exists; generic compatibility behavior is not allowed
to silently downgrade production to value-only safety.

Static Vset/Iset/OVP/OCP are different: their timestamps are not runtime heartbeats
because a valid unchanged configuration may remain unchanged for hours. Their actual
values and protection geometry are nevertheless re-read and revalidated by the runtime
envelope.

### Preflight and programmed-readback freshness were conflated

Before this audit `snapshot_from_live()` age-gated any exposed Vset/Iset/OVP/OCP value.
That can reject a perfectly valid new charge after a long idle period, before those old
setpoints have even been replaced. The same problem applied to a stable measured
`V_OUT=0` entity while Output was OFF.

The safety transaction now distinguishes the phases:

- preflight requires fresh dynamic physical/status safety evidence but does not require
  old static setpoint timestamps to be recent;
- measured V_OUT is a freshness-critical hard-envelope input only when Output is ON;
- after programming, Vset/Iset/OVP/OCP must be freshly observed before physical ON;
- post-enable verification again requires fresh programmed readback plus energized
  measured V_OUT.

Thus stale idle configuration cannot create a false start lockout, while stale readback
of a just-written configuration still prevents Output ON.

### HA per-entity fallback lost heartbeat semantics

The normal bulk `/api/states` path had access to HA `last_reported`, but the per-entity
fallback only retained `last_updated`. When a sensor/state stayed numerically unchanged,
a bulk endpoint failure could therefore turn a healthy source into a false stale trip.

`HassClient` now treats `last_reported` as a native adapter field on both paths and uses
it first when calculating source age. `last_updated` remains a compatibility fallback.
The production V2 monkey-patch is therefore defense-in-depth/adapter compatibility, not
the only place where heartbeat semantics exist.

The fallback also no longer fetches all mapped HA entities serially. It uses the existing
concurrent `get_states()` path, so one bulk-endpoint failure cannot multiply the 10 s
per-request timeout across dozens of sequential entities and stall the safety loop for
minutes. One slow/failing HA request group can still cost up to the client timeout and
must be measured on the bench, but the failure is bounded to the concurrent batch rather
than N serial timeouts.

Home Assistant `last_reported` is the preferred heartbeat timestamp because it advances
when the integration reports an entity even if its state value did not change.
`last_updated` remains a compatibility fallback for older/degraded adapters. This avoids
false shutdowns on genuinely flat temperature, current, switch or status values while
still detecting a sensor/integration that stopped reporting.

### Legacy exception cleanup could retire the FSM after an unconfirmed OFF

The preserved `bot_legacy.py` data logger has a historical exception path that attempts
`turn_off()`, suppresses shutdown exceptions, and then may call
`charge_controller.stop(clear_session=False)`. Under a verified-OFF adapter that is safe
when shutdown succeeds, but if physical OFF is not confirmed it can retire chemistry
state before hardware state is known.

Production V2 now treats runtime `_off_unconfirmed` as independent containment authority.
It is checked before ordinary telemetry/orphan handling. Even if the chemistry controller
has already become inactive, the guard does **not** enter the normal orphan grace path:
it repeats the verified shutdown transaction until Output is positively observed OFF.
Only after OFF proof is the containment flag cleared and the edge lease disarmed.
This closes the legacy exception path without modifying the V1 reference runtime.

### RecoveryOrchestrator could retire authority without verified OFF

The auxiliary `RecoveryOrchestrator` already used the protected enable path but its
runtime-start failure, `complete()`, and `abort()` lifecycle did not uniformly require
positive OFF confirmation. A false/raised `turn_off()` could therefore leave a possibly
energized output while runtime/authorization state was cleared, and `abort(turn_output_off=False)`
was an explicit software-only retirement bypass.

The orchestrator now retains the authorization as containment immediately after safe
enable. Runtime-start failure clears it only after verified OFF. `complete()` requires
verified OFF before completing/persisting and retiring the runtime. `abort()` likewise
requires verified OFF and no longer accepts a software-only retirement bypass. If OFF
is false or raises, runtime/authorization remain active and a new start is rejected.
This class is not the current production bootstrap path, but it is now safe to keep as a
future/auxiliary actuator surface rather than leaving a latent bypass.

The edge safety lease remains a separate direct-Modbus/output-register proof and is not
replaced by HA freshness or software containment.

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
HA `last_reported` cadence for unchanged values, bulk-to-fallback behavior, stale
physical/status/regulation source fault injection, failed-OFF containment retry,
edge-lease fault injection, Cooling restart, interrupted/cancelled Manual/probe recovery
and real charge traces.

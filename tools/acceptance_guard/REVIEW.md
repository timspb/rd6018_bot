# Acceptance integration review

Scope: supplemental D061 sink gating paired with pinned canonical source
`594a386e2b9fdd6bde9ebb15a5dfab30155291d6` (875-file manifest).
The earlier successful 2026-10-13 physical smoke used exact source `19577fc`
with its separately reviewed overlay; that historical evidence is not a
physical revalidation of every later `main` commit. Production is not mutated
by importing or testing this acceptance package.
These subclasses are acceptance dependencies, not a replacement runtime or
production entrypoint. No production file imports this package. `assemble`
binds the existing deferred client before canonical bot.py composes its owners;
`ProductionComposition.run` receives the guarded control server through its
existing lifecycle argument. The original server is never started.

Sink review: Hass switch ON/OFF and voltage, HA connector ON/voltage, native
connector ON/voltage are all intercepted before the original method calls I/O.
HA/native ordinary OFF is also gated. Nested client/backend dispatch uses a
task-bound permit for one operation, preventing duplicate gates and preventing
child tasks inheriting authority. Exceptions, False delivery and cancellation
retain pending ambiguity. Only a new post-command target report clears it.

Dwell is last distinct report minus first actual observation >=12 s, with <=8 s source
and observation gaps and no future/stale/invalid/cached report credit. Delayed
initial reports cannot backdate the observed stability window. Reading a
cache never counts as a new report. Native reports come from the canonical
subscription callback and invalidate on disconnect. HA reports require advancing
last_reported. Since #65, canonical native `get_live_values` includes
actual subscription callback timestamps, not synthetic cache-read freshness.
The guarded native sink observes the callback directly; reading cached state
does not grant additional dwell. No additional poller is created.

Voltage <=15.5 V remains mandatory; this Leoch Ca/Ca D061 pairing conservatively
uses <=14.7 V ordinary recipe authority. Original safe_enable_output and
SafeOutputCoordinator policy/readback/ownership checks remain installed. No
raw connector enable operation is exposed through the control server.

The canonical turn_off API does not encode ordinary versus fault reasons.
Its containment semantics must remain immediate, including real D061 coordinator
fault cleanup through the execution port. GuardedD061Control marks
only the typed d061_verified_stop operation as ordinary, checking dwell before
the coordinator persists OFF_PENDING. Direct supplemental low-level OFF is
ordinary by default. Canonical turn_off, safe_enable_output failure rollback,
and turn_on post-verification rollback
carry task-local fault-OFF scope and do no clock, dwell, journal, filesystem or
telemetry work before invoking the original OFF sink. A containment OFF latches
the acceptance guard against subsequent ON/voltage writes. This pairing is
limited to D061. An acceptance outer middleware on the existing Dispatcher
does not dispatch Telegram updates during the monitored window. Only the typed
D061 socket operations are available; this server has no arbitrary AUTO/Manual
start or reconfiguration and no D062 extensions. The unchanged canonical runtime
keeps its one poller and all background fault protections.
GuardedRuntimeSafety is installed using the canonical owner install contract,
before bot.py composition. It adds scopes only: explicit ordinary stops retain
their permit through verification/retries; direct canonical fault cleanup has
no acceptance clock or dwell dependency. Explicit HANDS_OFF operator OFF is
ordinary unless already executing fault containment. Extending the procedure
requires further typed operation classification and tests. This is not a claim
of unrestricted Telegram/AUTO acceptance.
Adoption/fault socket operations carry fault-OFF scope so ambiguous edge cleanup
also remains immediate when the durable ownership is still HANDS_OFF.

Physical launch gates: current present monitor, operable emergency power cutoff,
identified Leoch_72Ah Ca/Ca battery and sensor placement, and exact compiled/flashed
D061 firmware identification. The real-node live-adoption/900 s/raw-protection
bench cases are the acceptance target, not a prerequisite PASS invented from
these tests. Production deployment still requires their physical evidence.
Firmware version or unit PASS alone cannot establish those gates. Stop actuation
when any physical prerequisite is missing; read-only inspection can continue.

Handover remains the prior transient-unit procedure: verify the original
production backup, stop production only for a ready supervised window, prove
zero bot processes, use isolated state, launch this dependency pairing through
the exact bot.py composition, then prove independent startup OFF. Exactly one
poller. No change to production tree, marker, environment or service unit.
The launch library independently checks stopped production, absence of bot.py
processes and the isolated state directory, then holds an exclusive OS poller
lock through canonical lifecycle execution. Caller readiness booleans cannot
bypass a running production service.
External ON setup still requires its own canonical-policy-approved guarded
procedure; it is not an API in this package. No hardware ON is authorized by
calling assemble or by passing software tests. Final OFF/lease/ownership proof
is required before restoring the original production service.

## Approved transient executor

The live entrypoint is `python3 -m tools.acceptance_guard.transient` from the
deployment checkout. It builds the existing guarded production connector and
`EdgeSafetyLease`; the reusable executor API is `TransientAcceptance.run()`.
The command requires safe target/duration arguments and explicit current
physical readiness acknowledgements. It performs fresh dual-source OFF
preflight, arms rollback before calling
the production stop callback, verifies service stop and sole poller ownership,
then arms the existing edge lease. Programming and ON use only guarded
canonical `HassClient.safe_enable_output()`. Every exit attempts immediate
canonical OFF, independently proves OFF, disarms the lease only after proof,
and restores production only after OFF and lease-release proof. A failed stop
is not followed by an attempted service restart. The API exposes no direct
HA/ESP ON or force-on route.

Example command (the operator selects the current target and duration):

```bash
python3 -m tools.acceptance_guard.transient \
  --voltage-v 14.4 --current-a 0.2 --ovp-v 15.0 --ocp-a 0.4 --duration-s 60 \
  --confirm-physical-preflight --confirm-cutoff-tested \
  --confirm-temperature-sensor --confirm-supervised
```

This command was not run as part of software implementation; it stops the
production service and can energize the physical output after all gates pass.

The absolute programmed-voltage ceiling is 15.5 V; the programmed battery
voltage for this Leoch Ca/Ca window is limited to 14.7 V. OVP must remain above
the target and at or below 15.5 V. Ordinary transitions retain the guard's 12
second fresh report dwell; emergency OFF remains immediate. Calling `run()`
does not replace any physical gate or constitute physical validation.

## D061 first guarded negative scenario — synthetic protection evidence loss

The existing **positive** D061 takeover is unchanged and remains the default.
A separate, explicitly selected negative acceptance mode is available:

```
python tools/run_d061_takeover_smoke.py --physical-ready --fault-operation d061_fault_raw_protection_unavailable
```

This is **a real electrical ON/OFF acceptance window** if executed on node104.
Never run it without the same current supervised bench, physical emergency cutoff,
independent HA102/ESP128 OFF proof, root-owned exclusive D061 lock, and verified
production handover required by the positive scenario. Keep the hardware output
and service untouched during offline tests and CI.

The mode performs the same canonical safe enable, lease release, typed battery
adoption and positive post-adoption proof. It then injects **only an in-process
unavailable raw-protection evidence response** through the existing typed
`PhysicalTestControl`. It does **not** modify the real RD6018 register 16,
assert OVP/OCP/OPP, alter sensor timestamps, or program different V/I/OVP/OCP.
After the typed fault, a PASS requires all of the following:

- An explicit typed acknowledgement of containment and Output OFF, with the
  edge lease reported disarmed; the fault is called exactly once.
- Fresh independently sourced HA and native ESP Output OFF plus physical
  output voltage/current converged to zero, a fresh normal raw protection code,
  and preserved V/I/OVP/OCP programmed readback.
- Canonical adoption/manual ownership retirement and a coherent lease
  generation; stopped acceptance runtime; restored original single-owner
  production service.

Any invalid or ambiguous response, remaining Output ON, stale/unknown source,
armed lease, unresolved ownership, failed cleanup or incomplete production
restoration is FAIL/HOLD, **never PASS**. The global owner lock remains held
through the entire negative test and its failure containment. Retain on-node
root-owned evidence when cleanup is unresolved.

**Do not interpret a PASS for this mode as physical OVP, OCP or OPP trip
acceptance.** Those hardware-register assertions, out-of-band authority
changes, and adopted-bot kill/restart need separate physically reviewed
procedures tracked in issue #68.

## D061 negative matrix candidate gate (2026-10-14)

The two deterministic hooks `d061_fault_toctou_precommand` and
`d061_fault_ambiguous_edge_ack` exist in `PhysicalTestControl`, but are not
enabled by the supervised launcher. Its accepted takeover overlay and exact
source are byte-pinned. Keep those positive/raw-protection pins unchanged;
the current launcher must reject any altered supplemental bytes. Supporting
these two scenarios requires a separate reviewed candidate SHA and explicit
overlay attestation, with offline fake-backed tests for the complete
containment/restore path. Do not use working-tree source as an implicit
overlay or report a test-only result as physical acceptance. The detailed
expected acknowledgements and remaining physical matrix are recorded in
`../../docs/assistant/D061_NEGATIVE_MATRIX_ENGINEERING_2026-10-14.md`.

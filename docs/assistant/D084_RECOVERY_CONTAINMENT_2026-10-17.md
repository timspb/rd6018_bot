# D084 — Recovery Containment: software owner gate (2026-10-17)

Canonical base: D083 merge `1609312afd0e507cfd9646f1095d35093609d450`.

## Scope and ownership

D081 charge-domain recovery policy selects the route and decides admission.
D082 application `SessionRecoveryService` performs ordered actions via the
**existing** `ExecutionPort`. D083 requires verified success before publishing
RESTORE. D084 adds a **pure application lifecycle quarantine**
(`application/recovery_containment.py`), rather than a second hardware owner.

The first unconfirmed boolean result from an attempted A/B/C restoration latches
an in-process, immutable incident (route + failed step). While latched,
`data_logger` continues polling telemetry, recording observations, and running
independent safety/verified-emergency-OFF checks, but does **not** enter a new
automatic restoration or a normal `charge_controller.tick`/action batch.
The first failed iteration unwinds the shared execution-owner lock before the
next poll. Later polls sleep outside this lock, so operator and emergency
execution routes are not held hostage by the quarantine.

For active route A, rejected voltage/current setter results now prevent a later
`request_verified_on` call. B/C preserve D083's short-circuit verification.
The known successful A/B/C order, approved setpoints, restore authority,
temperature/OVP/OCP guards, thresholds and all charge strategies remain
unchanged. Neither the quarantine nor this extraction sends an additional
physical command, disarms the edge lease, changes its 900-second TTL / 300-second
renew cadence, or treats an ambiguous physical Output as OFF.

## Release and residual blockers

**No automatic release is implemented.** Ordinary clear-looking telemetry is
not proof of a new operator/session authority and never clears the latch.
The D084 gate is intentionally **process-local**. It does NOT yet survive a
process restart; startup deferred restoration, explicit START admission and the
matching durable identity/edge acknowledgement are separate owners. An exact
reboot/restart/re-admission acceptance test and a durable, authorized release
contract are required before deploying D084 as the final safety solution.

Execution exceptions still flow to the established outer `data_logger` safety
handler; the new quarantine explicitly covers **unconfirmed boolean returns**,
not every raised exception. Whether the independent lease is renewed or allowed
to expire when quarantined is not modified here; physical edge/Modbus behavior
must be demonstrated on a safe bench before enabling this change on node104.
An energized RD6018 with a permanently unavailable control path remains outside
what Python-only logic can physically guarantee.

## Test/evidence scope

Unit tests cover sticky first-denial semantics, immutability, B denied ON
across multiple polls (one ON attempt), C SAFE_WAIT denied OFF (no subsequent
setpoint/ON), successful admission, and the two source-wiring gates around the
shared-lock restoration and tick. The application service tests cover route A
rejected setpoints without any ON request. CI on Python 3.10, 3.11 and 3.12
is required prior to merge.

**Software changes only.** No node104, PSU, battery, HA, ESPHome, firmware or
production instance was operated. A passing CI result is not a physical PASS.

# D082 — session recovery execution owner

## Ownership boundary

D081 moved only deterministic route and authorization decisions to
`runtime.charge.link_session_recovery`. D082 moves the remaining physical
restore choreography into `application.session_recovery_service` without
moving the surrounding session-recovery orchestration.

```text
runtime.production_runtime.data_logger
  telemetry + pause gate + D081 route/authority + target selection
  persisted try_restore_session + time correction + checkpoint + logs/notices
  holds the canonical execution owner lock
       |
       v
application.SessionRecoveryService
  route-specific phase-protection / setpoint / verified OFF or ON sequence
       |
       v
application.ExecutionPort (existing app-scoped port)
       |
       v
existing execution owner / safe enable and verified readback boundary
```

The service is composed only inside an active recovery branch while the
canonical execution lock is held; the current app-scoped port is resolved anew
after any owner rebind, not cached at logger startup.

The service receives the already composed execution port, phase-protection
operation, and current cap as explicit dependencies. It does not import
production runtime, Telegram, HA, or transport modules. It is an application
execution use case, not a second port, hardware gateway, policy engine, or
startup coordinator. `data_logger` still holds the same owner lock around route
selection, restore, and service invocation; no lock boundary or call order
outside the extracted sequences changed.

## Preserved route behavior

- **A — active lost-link session:** phase protection, voltage, capped current,
  verified ON. The service returns the enable result; runtime updates active
  output state only when it is confirmed. Restore time correction, checkpoint,
  event, notice, and log remain in runtime.
- **B — restored IDLE after lost link:** persistence restore and its existing
  ordering remain in runtime. SAFE_WAIT runs phase protection, voltage, capped
  current, verified OFF. Other authorized stages run the same first three steps
  then request verified ON. As before, runtime does not branch on that ON
  result before its existing RESTORE event/notice/log behavior.
- **C — restored IDLE with Output already ON:** SAFE_WAIT runs phase
  protection, verified OFF, voltage, capped current. Other authorized stages
  run phase protection, voltage, capped current. This route never requests ON.

Targets, temperature handling, capped-current policy, action authorization,
operator pause, safety alarms, time corrections, persisted restore, and all
user-facing effects remain where they were. Setter and phase-protection
exceptions continue to propagate through the existing runtime error handling.
The service deliberately preserves existing ignored boolean results for B/C
setters/OFF/ON; it does not claim stronger acceptance semantics.

## Evidence and limits

Independent service tests use an inert fake port and assert exact ordered calls
for A success/failure, B SAFE_WAIT/normal, C SAFE_WAIT/normal, no second ON,
and propagated errors. A runtime wiring guard confirms all three recovery
routes delegate to the service and that their duplicated physical sequences
are absent from the recovery block. D081 pure route tests remain authoritative
for route selection and authorization.

This is software-only evidence. No node, HA, ESPHome, firmware, PSU, battery,
credential, lease, or physical Output action was used. It does not establish
physical safety or alter any watchdog, lease, recipe, threshold, session, or
enable authorization behavior. The legacy B behavior that logs/notifies after
an ignored false ON result remains a known limitation by design in this
extraction; changing it requires a separate behavior change and tests.

Remaining work is to continue identifying cohesive production ownership seams
without moving hardware ownership out of the existing execution port or
expanding this service into a generic recovery framework. Full supported-Python
CI and any required bench gates remain external validation boundaries.

# D085 — durable recovery quarantine

## Owner and ordering

`runtime.journal.recovery_quarantine.RecoveryQuarantineJournal` is the
single persistence owner for `session_recovery_quarantine.json`, stored beside
the canonical charge session file. It writes a versioned document with its
explicit owner, first incident reason, UTC incident time, and available session
and battery identity. It uses the existing crash durable `atomic_session_write`
primitive and never reads or writes `charge_session.json`.

`production_bootstrap.install_production(app)` loads this journal and injects
the resulting state and synchronous persistence callback into the app-scoped
`SessionRecoveryGuard` before creating/reusing the canonical `ExecutionPort`.
The startup lifecycle checks the guard before controller restore; deferred
restore, START and normal controller tick are similarly blocked by the same
guard. Telemetry and independent verified OFF handling remain available. A
first ambiguous false result or exception latches RAM before synchronously
writing the incident. A write failure propagates; it cannot return recovery
success or release the in-memory interlock. Subsequent polls do not rewrite the
journal. Durable mode disables the process-only `operator_rearm` method.

```text
composition -> production_bootstrap -> journal load -> SessionRecoveryGuard
                                                  -> canonical ExecutionPort
startup/deferred restore, START, normal tick ----> guard
ambiguous recovery failure ----------------------> RAM latch -> journal write
```

There is no UI rearm path. Clearance requires a future D086 owner that proves
physical Output OFF and operator authority, then atomically retires durable and
in-memory quarantine together.

## Limits and acceptance

The journal does not claim protection if the journal is deleted/lost, or for a
process crash in the interval between ambiguous physical actuation and a failed
journal write. A present malformed, unreadable, unknown-owner, or unknown-schema
journal fails closed. No telemetry observation releases quarantine.

This change is software-only. It adds no physical command or ON authority and
does not change charge algorithms, normal successful A/B/C ordering, edge lease,
or emergency OFF handling. It does not validate HA, ESPHome, node 104, RD6018,
or physical Output behavior; deployment/acceptance still requires the separate
physical and edge validation gates documented by the project.

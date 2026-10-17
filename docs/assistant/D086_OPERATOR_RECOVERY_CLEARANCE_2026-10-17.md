# D086 — operator recovery clearance boundary

## Accepted software boundary

D086 adds a narrow application coordinator at
`application.operator_recovery_clearance.OperatorRecoveryClearanceService` and
extends the existing `runtime.journal.recovery_quarantine` owner with a durable
retirement tombstone (schema 2). The incident format remains schema 1 and keeps
its owner identifier. A tombstone is accepted on boot only when its owner,
schema, state, operator ID, retired session ID, OFF evidence, and timestamp are
present and valid. A malformed/present journal remains quarantined; only a
genuinely absent journal means a fresh install. The journal is never unlinked.

The service requires the canonical ExecutionPort and its already-bound
application owner lock. It has no production authority, verified-OFF evidence,
or session-retirement provider wired. Missing providers deny clearance. An
authority must return `AuthorizedRecoveryOperator`; an arbitrary context or
boolean is not accepted. The OFF port must return a fresh, typed
`VerifiedOffEvidence` (30 second bound), and retirement must return a matching
`RetiredControllerSession`. The real ExecutionPort does not yet provide the
typed OFF receipt, and no production authority or durable retirement owner
exists. Therefore this is a fake-port contract only and remains unavailable to
production. The sequence is OFF proof, controller session retirement,
atomic/fsynced journal tombstone, then coordinator-only in-memory guard release.
Failure after session retirement but before tombstone leaves the RAM guard
latched and the incident journal intact. No service wiring or UI was added.

## Admission gap and remaining work

Repository inspection found no canonical operator authorization owner or
configured administrator identity. Telegram user IDs are available but do not
prove authority. The controller's existing `stop(clear_session=True)` path
does not report whether persistence deletion succeeded, so it is not suitable
as a clearance retirement proof. Therefore production wiring and UI are
deliberately disabled. No operator can currently clear a durable quarantine
through D086; this is the safe outcome until both missing owners are exposed
through trusted, testable contracts. Do not activate the service with an
ad-hoc callback or caller-supplied boolean.

## Crash behavior and limits

Retirement requires a readable schema 1 incident, known nonblank session
identity matching the request, valid provenance, and matching battery binding
when recorded. The tombstone binds back to the original incident ID/reason and
battery; unknown fields, missing fields, malformed evidence, and mismatched
bindings fail closed. D085 incidents created before session identity or the new
incident ID was recorded remain quarantined and cannot be retired by this path;
they require a separate, explicit operator recovery resolution before any
future activation. Tombstones rely on the ordered, verified controller-owned
session retirement performed by the caller; the journal cannot inspect the
external controller session file. Atomic replacement and file/directory fsync
use the existing `atomic_session_write`. The journal assumes a single-process
writer under the owner lock; external concurrent mutation is outside that
serialization contract. A missing journal remains indistinguishable from a
fresh install. No physical acceptance is claimed. No node, HA/ESPHome, PSU,
Modbus, firmware, lease, chemistry, or live production behavior was touched.

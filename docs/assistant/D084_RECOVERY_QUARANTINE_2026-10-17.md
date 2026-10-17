# D084 — ambiguous recovery quarantine

## Behavior

`application.SessionRecoveryGuard` owns a sticky, process-lifetime quarantine.
`SessionRecoveryService` enters it after a false result from any route A/B/C
physical prerequisite or after an execution exception; the exception still
propagates to the existing outer `data_logger` handler. A denied preflight does
not itself enter quarantine. Once entered, the same polling cycle skips the
controller tick, and every later cycle skips link-session restoration and the
tick even if telemetry looks normal or the peer reconnects.

The app-scoped `ExecutionPort` also denies automatic ON, V/I, OVP/OCP, and
controller-action writes while quarantined. This covers production startup
restore and operator/manual callers that share the canonical port. Verified
OFF remains available; independent OVP/OCP/temperature handling and configured
manual OFF conditions run before the interlock. Telemetry, lease renewal,
native monitoring, and safety observation continue. The controller session is
not stopped or cleared after a false recovery result, and quarantine does not
issue retry OFF commands or infer Output OFF from unknown/stale telemetry.

## Release and limitation

There is no UI rearm action in D084. The guard exposes only an explicit
operator-rearm operation that requires the caller to supply positive confirmed
Output-OFF evidence; no telemetry poll, reconnection, or automatic lifecycle
path calls it. Until a separately reviewed operator workflow is added, a
quarantined process remains locked for its lifetime. **The quarantine is not
durable across process restart.** A restart can construct a new clear guard and
may use the existing startup restore authority. D084 therefore does not claim
restart protection; durable persistence and a safe operator clearance flow
remain blocked for a follow-up design with the canonical persistence owner.

The 900-second ESPHome lease and 300-second renewal behavior are unchanged.
This is software-only evidence; it does not validate node 104, the edge package,
HA/ESPHome, PSU, or physical Output behavior. Exact node/firmware bench
acceptance remains required before production use.

## Evidence

Offline tests cover sticky state, guarded rearm, all restore service result
paths, retry suppression, exception propagation, and runtime source wiring.
Focused unit tests and Python compilation are the local validation boundary.

# RD6018 V3 Canonical Event Timeline Model — WORKSTREAM 14.2

## Purpose

Provide one read-only event representation for UI, shadow comparison and parity
analysis. This model normalizes existing sources; it does not rewrite V2 data or
change runtime ownership.

## Event contract

`CanonicalChargeEvent` contains event identity, timestamp, session/trace IDs,
source, typed event type, phase before/after, profile, reason, severity,
activity classification and metadata.

Sources are `domain`, `journal`, `legacy history`, `telemetry`, `manual` and
`safety`.

## Taxonomy and reasons

Session, phase, strategy, control, safety and recovery events are separate. A
session stop is not a phase stop. Reasons are typed by concern: session stop,
phase transition, control, safety and migration.

## Normalization rules

- `active -> stopped -> cooling -> arming -> active` is a phase/session
  transition sequence; the historical stop reason does not make the current
  session stopped.
- Manual transition is not automatically a fault.
- Historical event is not active state.
- `EMERGENCY_UNAVAILABLE` without current confirmation is `FAULT_DETECTED` with
  activity `HISTORICAL`, not an active safety latch.
- Events are ordered by timestamp and event ID and filtered by session ID.

## UI and shadow boundary

UI receives only `CanonicalTimelineSnapshot` with session ID, current phase,
ordered events, current state and active alerts. It does not read journal,
`charging_history.log` or runtime internals.

Shadow comparison consumes the canonical event stream and retains MATCH,
EXPECTED_DIFFERENCE, WARNING or BLOCKER classifications.

## Status

**CANONICAL_EVENT_TIMELINE_READY.** Pure contracts and tests are present. No V2
runtime, START/ACTIVE behavior, HA, ESPHome, lease or physical output changed.


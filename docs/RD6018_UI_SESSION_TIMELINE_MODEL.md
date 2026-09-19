# RD6018 V3 UI Session Timeline & Visualization Model

## Boundary

```text
V3 Domain Events -> SessionTimeline -> Current View Model -> UI Adapter -> UI
```

UI is presentation-only. It does not own charge logic, FSM transitions, safety
decisions, actuator state or telemetry arbitration, and the pure session module
does not import runtime, application, HA, ESPHome or execution modules.

## Session boundary

`SessionTimeline.start()` creates a new `session_id`, start timestamp, empty
event timeline and empty `SessionGraphBuffer`. Starting a new session replaces
the previous presentation state; old data is retained only by an outer archive
system, never by the current view or graph.

`SessionViewModel` exposes session id, start, phase, elapsed time and explicit
state: `UNKNOWN`, `WAITING`, `ACTIVE`, `COMPLETED` or `FAILED`.

## Timeline events

`ChargeTimelineEvent` is immutable, session-scoped and sequence-numbered. It
covers session start/stop, phase changes, Delta start/completion, Hold
start/completion, charge completion and fault events. Event payloads carry
domain facts such as voltage/current/timestamp, not UI decisions.

`OperatorTimelineFormatter` orders by timestamp and sequence and exposes only
the operator event contract. Streaming telemetry ticks and internal FSM loops
are not created by this UI layer.

## Graph isolation

`SessionGraphBuffer` carries its `session_id`, samples and phase markers. A
marker from another session is rejected. A new session starts with no samples
or markers; time offsets begin at zero.

## Current charge view

`CurrentChargeSnapshot` is the single presentation shape for session, charge
profile/phase/strategy, measurements, last transitions and safety status. The
UI adapter consumes this snapshot rather than reading runtime state or hardware.

## Empty/broken data

Missing/invalid state is represented explicitly by enum values and typed
events. Empty strings are not used as state values. Faults and failed stops are
visible as `FAULT_EVENT`/`FAILED`.

## Validation

`tests/test_workstream8_ui_session.py` covers new-session reset, transition,
Delta/Hold visibility, stop/fault state, graph isolation, ordering, forbidden
imports and no physical calls.

Status: `UI_SESSION_MODEL_READY` for the pure V3 presentation contract. This
does not change V2 UI/runtime and is not a production ownership transfer.

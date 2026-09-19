# RD6018 Bounded Live Shadow Observation Protocol

Статус: **LIVE_OBSERVATION_PROTOCOL_READY**

Назначение: получить фактическую V2-owned цепочку lifecycle и сравнить её с V3
shadow без управления системой. Протокол не инициирует заряд, не продлевает
lease и не меняет ownership.

## 1. Observation window

### Start condition

Окно открывается после успешного read-only warm-up всех доступных источников и
до естественного V2 `START`. Observer не создаёт START и не вызывает UI/control
handlers. Если система уже `ACTIVE`, окно фиксируется как partial-current-state
и не используется для доказательства предыдущих переходов.

### Sources

| Source | Read-only data |
|---|---|
| V2 node 101 | current persisted/manual state, journal/history, legacy status |
| HA 102 | entities, timestamps, telemetry/readback, protection, lease indicators |
| ESPHome 1.28 | direct entity state, availability, timestamps, output/readback, lease observation |
| RD readback | observed voltage/current/output/mode/temperature when exposed by source |
| V3 shadow | normalized snapshot, parity view, diagnostics; no control surface |

### Snapshot frequency

Protocol target: one read-only observation snapshot every **1 second** while
waiting for an event, with source timestamps preserved as authoritative. Event
polling and snapshot collection must not fabricate evenly spaced timestamps;
missing/stale source data is marked `UNKNOWN`. If a source cannot sustain the
target cadence, its actual timestamp and freshness are recorded.

### Correlation

1. Use validated `session_id` and `trace_id` from the event source.
2. Join telemetry/readback only when source timestamp and session range agree.
3. If V2 legacy state has no identity, store `legacy_status=LEGACY_NO_IDENTITY`
   and leave `session_id`/`trace_id` unknown.
4. Never synthesize identity, START or phase transition to fill a gap.

## 2. Required snapshot fields

Every accepted observation record contains:

| Group | Required fields |
|---|---|
| Session | session_id, trace_id, legacy_status, timestamp |
| State | program, phase, lifecycle |
| Telemetry | voltage, current, power, temperature, CC/CV, source, freshness |
| Safety | protection code/state, lease owner/state/expiry observation, freshness |
| Provenance | source, captured_at, confidence, read-only mode |

Absent values are explicit `UNKNOWN`/`MISSING`, never copied from an older
session without provenance.

## 3. Event capture

Capture only events observed at the source boundary:

```text
START
  -> phase transition
  -> Delta start
  -> Delta completion
  -> Hold start
  -> Hold completion
  -> termination
  -> STOP
```

For each event store timestamp, source, session/trace identity or explicit
legacy absence, previous/next state, reason, conditions, correlated telemetry
and safety snapshot. A stable value is not an event; a current phase is not
proof of how it was entered. No reconstruction, interpolation or inference is
allowed.

## 4. V2/V3 parity result

Each observed event receives exactly one classification:

- `MATCH` — V2 event/state and V3 shadow event/state agree;
- `EXPECTED_DIFFERENCE` — documented semantic difference with evidence;
- `DIVERGENCE` — both sides are observed but disagree without accepted reason;
- `UNKNOWN` — event, identity, timestamp or required source evidence missing.

V3 output is report-only. It cannot write into V2 state, alter a program,
renew/disarm lease or submit an intent.

## 5. Window completion and abort rules

Window is complete only after a real `STOP` is observed, or is explicitly
marked `PARTIAL` if the observation ends before termination. It is invalid for
full lifecycle coverage when:

- observer started after START;
- any required event was inferred rather than observed;
- session/trace changes are ambiguous;
- telemetry/readback is stale at a required event;
- sources disagree and no owner/source can resolve the conflict.

An operator may stop the observer process, but the protocol never sends a
charge STOP command. Safety faults are observed and escalated through the
existing V2 safety path; this observer does not act on them.

## 6. Safety boundary

The protocol performs only HA GET/state reads, ESPHome state reads, RD
readback observations and local normalization. It performs no START/STOP,
setpoint write, service call, lease operation, deployment, restart or physical
command.

## 7. Acceptance

`LIVE_OBSERVATION_PROTOCOL_READY` means the bounded capture procedure and
evidence schema are defined. It does not claim that a complete lifecycle has
already been observed. Full transition coverage remains pending until a real
pre-START window captures every required event with valid correlation.

# RD6018 Live State Consistency Report — WORKSTREAM 14.1

## Result

**STATE_CONSISTENCY_VALIDATED** for the observed current state, with an
observability/history namespace issue recorded as technical debt.

No runtime, ownership, command or physical state was changed.

## State ownership

| State | Current owner | Evidence |
|---|---|---|
| Physical Output | V2 physical path; RD/ESPHome edge is final dead-man boundary | HA output/state and lease entities |
| Session lifecycle | `ProductionManualSessionManager` / manual runtime | `MANUAL_TRANSITION` journal |
| Phase/stage | manual runtime session authority | JSON snapshot and journal |
| Persisted session | manual runtime writer; snapshot is not physical truth | `manual_session_v2.json` |
| Emergency presentation | V2 history/logging path | `charging_history.log` and V2 formatting |
| Physical OFF verification | V2 `SafeOutputCoordinator` / readback path | journal `Output OFF confirmed` |

`ACTIVE` is asserted after `safe_enable_confirmed` and must agree with fresh
physical readback. `STOP`/`COMPLETE` are session events; they do not alone prove
physical Output OFF.

## Apparent STOP versus active Output

The persisted file is not currently `STOPPED`; it contains:

- `state: active`;
- `stage: mix`;
- `started_at: 2026-09-15T06:07:21Z`;
- `saved_at: 2026-09-15T06:10:39Z`;
- `stop_reason: manual_main_hold_complete`.

The `stop_reason` is historical metadata from the Main-to-Mix transition. The
journal proves:

```text
06:10:26  Output OFF requested
06:10:30  Output OFF confirmed
06:10:31  active -> stopped (manual_main_hold_complete)
06:10:31  stopped -> cooling -> arming
06:10:39  arming -> active (cooling_resume_confirmed)
06:10:44+ CC minimum evidence / Mix voltage ramp
```

The physical state (`Output ON`, CC, `17.17 V / 3.49 A`) therefore matches the
later active Mix state. Classification: **EXPECTED TRANSITION**.

## History completeness

This is a namespace mismatch, not proof that transitions never occurred:

- `charging_history.log` contains coarse session/restore and emergency records;
- manual START, STOP, cooling, arming, active, minimum/maximum and hold
  evidence are written to systemd journal under `rd6018.manual`;
- the journal contains the current transitions, but the Telegram/history file
  does not reconstruct them as one chain.

Classification: **LEGACY/OBSERVABILITY ARTIFACT** and **MISSING EVENT PROJECTION**.

## `EMERGENCY_UNAVAILABLE`

The marker appears in `charging_history.log` at `2026-09-15 03:15:02`, stage
`Idle`, with zero measurements. The current V2 code contains presentation-side
grouping/suppression for this event, but the line alone does not identify a
contemporaneous physical emergency action.

At the live observation the lease was armed, tripped `off`, boot quarantine
`off`, Modbus age `3.582 s`, protection code `0`, and output state code `1`.
No active emergency latch is evidenced now. The historical marker's exact
trigger remains **UNKNOWN** and must not be inferred from the marker alone.

## V3 impact

- current physical/session consistency: **validated**;
- V3 parity: **WARNING** until journal and history share trace/session IDs;
- migration: **observability blocker**, not evidence of physical ownership loss;
- required improvement: one read-only event projection for lifecycle, physical
  verification, lease and emergency markers.

## Conclusion

The RD is not shown to be running after a terminal stop. It was stopped at the
Main-to-Mix boundary and re-armed into active Mix eight seconds later. The real
defect is that `stop_reason` is easily misread as current state and manual
evidence is split between journal and charging history.

The canonical representation for this split is now defined in
`docs/RD6018_CANONICAL_EVENT_TIMELINE_MODEL.md`; the source records themselves
were not rewritten.

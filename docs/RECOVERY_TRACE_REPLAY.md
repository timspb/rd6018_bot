# Recovery trace replay

The V2 recovery layer can replay recorded RD6018 battery telemetry without touching hardware.
The replay path is deterministic: it runs the same `SignalAnalyzer` and `RecoverySessionTracker`
used by the recovery domain and produces cycle evidence plus a longitudinal trend.

## Run

```bash
python tools/replay_recovery.py recovery.json --pretty
```

## Input

The root object contains `cycles`. Each cycle identifies the physical battery and contains an
ordered `trace` of U/I/T samples. Timestamps are seconds on one monotonic/unix-style axis; only
their differences matter to signal analysis.

```json
{
  "cycles": [
    {
      "battery_id": "garage-efb-01",
      "started_at": 0,
      "completed_at": 7200,
      "intent": "recovery",
      "condition_before": "rehydrated",
      "measured_capacity_ah": 48.2,
      "cca_a": 512,
      "internal_resistance_mohm": 6.8,
      "notes": "cycle after refill",
      "trace": [
        {
          "timestamp_s": 0,
          "stage": "Main Charge",
          "voltage_v": 13.9,
          "current_a": 5.0,
          "temp_c": 22.4,
          "is_cv": false,
          "target_voltage_v": 14.8,
          "ah": 0.0
        },
        {
          "timestamp_s": 1800,
          "stage": "Main Charge",
          "voltage_v": 14.78,
          "current_a": 0.42,
          "temp_c": 23.1,
          "is_cv": true,
          "target_voltage_v": 14.8,
          "ah": 3.1
        },
        {
          "timestamp_s": 3600,
          "stage": "Mix Mode",
          "voltage_v": 16.45,
          "current_a": 0.21,
          "temp_c": 24.0,
          "is_cv": true,
          "target_voltage_v": 16.5,
          "ah": 3.5
        },
        {
          "timestamp_s": 3900,
          "stage": "relax",
          "voltage_v": 13.55,
          "current_a": 0.0,
          "temp_c": 23.8,
          "ah": 3.5
        }
      ]
    }
  ]
}
```

Supported `intent` values are `normal`, `recovery`, `conditioning`, and `diagnostic`.
Supported condition values are defined in `pb_domain.BatteryCondition`.

## Evidence

For each cycle the replay aggregates:

- Main target, global Main Imin, Ah accepted and time-to-target;
- high-voltage target, global HV Imin, time-to-target and confirmed current reversal;
- starting/max battery temperature and maximum positive dT/dt;
- relaxation voltage at 5 min, 15 min, 1 h, 12 h and 24 h when those samples exist;
- optional measured capacity, CCA and internal resistance supplied by an external test.

A voltage step inside one named stage (for example AGM 14.4 -> 14.6 V) starts a new signal-analysis
segment but does **not** erase the minimum current already observed for the whole Main/HV portion.

## Trend semantics

`Main Imin` and `HV Imin` are trajectory evidence only. A lower or higher Imin is not awarded a
health score by itself because its interpretation depends on recipe, hydration/wetting state,
temperature and where the battery is in the recovery sequence.

The health-oriented trend score is primarily driven by comparable capacity, CCA and internal
resistance measurements, with penalties for thermal instability. This makes repeated recovery
cycles auditable instead of turning one convenient electrical signal into a health claim.

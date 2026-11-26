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


## D090/D106 read-only proof type boundary (2026-11-19)

`tools/node104_d106_proof_types.py` is the pure owner of `TrialOffProof`, its existing fail-closed field validation, and the shared `TransactionError` class. The import graph is `D106 observer -> D106 projection -> pure proof types`; the D090 transaction imports and publicly re-exports those exact definitions while retaining its Unix `fcntl` transaction lock. Read-only proof consumers must not import the transaction lifecycle to obtain a DTO. This extraction does not alter Native/HA evidence requirements, D090 release/recovery gates, or authorize physical operations.


## 2026-11-19 — independent P7 D090/D106 pure proof DTO batch-28 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p7-d106-proof-boundary-luna-20261119-28` exit 0; R7.2 completion event observed. The pure `tools/node104_d106_proof_types.py` is the single owner of `TrialOffProof` and `TransactionError`; D090 continues public compatibility re-exports and strict `isinstance` transaction validation with its Unix `fcntl` lock intact, while D106 read-only projection no longer imports D090 transaction at all.
- Original Windows RED reproduced (`test_same_object_id_sensor_and_number_keep_independent_typed_cache_for_d106` imported D090 and raised `ModuleNotFoundError: fcntl`). After repair independent Windows project `.venv` full ESPHome/D106/HA/connector cohort **60 PASS + 7 subtests PASS** with no D106 deselection. Extended Windows Native+D106+production lifecycle/entrypoint/D061 cohort **90 PASS + 24 subtests PASS**, exit 0. Native Linux `python3 -m unittest tests.test_node104_d090_transaction tests.test_node104_d106_readonly_recovery tests.test_node104_d106_projection_portability -q`: **74 PASS**, exit 0; public class identity, refusal evidence and transaction safety exercised. Compile and `git diff --check` PASS.
- P7 read-only proof type boundary source/fake ACCEPTED. P7 overall PARTIAL, P8 full release/physical HOLD, AD083/AD148 whole-file HOLD. No node104/live HA/ESP, Output, setpoints, charge, lease, firmware, service/deployment or remote push.

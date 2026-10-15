# D063 — Passive voltage relaxation signature (EFB and Ca/Ca)

Status: **optional, standalone passive observer**. The accepted bot and its production service are not modified or restarted; the optional collector is installed and commissioned independently.

## Scope and isolation

The pure computation engine lives in `runtime/charge/observability/voltage_relaxation.py`. An independent service (`tools/voltage_relaxation_sidecar.py` and `tools/rd6018-voltage-relaxation.service`) reads existing HA/native telemetry every 30 s and reads the durable SAFE_WAIT session file. It issues **no hardware command**, alters no charge stage, and cannot influence the bot's control logic. It uses the existing `.env` and venv, but runs as its own unprivileged process.

Only stage `Безопасное ожидание` (canonical `STAGE_SAFE_WAIT`), profiles `EFB` and `Ca/Ca`, stage-continuation destination `MAIN` or `DONE`, and exact durable session identity plus SAFE_WAIT epoch are accepted. The persisted session file must have been modified within 10 minutes; without it no SAFE_WAIT is inferred. **AGM excluded entirely.** Manual sessions and operator pause are not logged.

**The recorder never extends SAFE_WAIT** for data collection. The stock SAFE_WAIT threshold or time limit may cause transition to MAIN or Storage within minutes; any unavailable 15–60-minute metric is marked `insufficient_data`, not fabricated. It does NOT record 12/24/36-hour open-circuit voltage because Storage turns the output back ON.

## Evidence qualification

Per sample (typically 30 s), record only:

- `battery_voltage` **from battery terminals**, not `voltage` (Output 0 V while OFF);
- `switch` explicitly reports OFF; unknown output is rejected, not assumed OFF;
- measured Output current is within 0–0.03 A;
- HA/native metadata on `battery_voltage`, `switch`, and `current` all say `status=ok` and `age_s ≤75`;
- voltage is finite/physical, timestamp is no earlier than the known SAFE_WAIT epoch;
- optional independent external temperature is recorded as observed, with missing/invalid temperature stored NULL (not zero).

Session, stage epoch, continuation and profile generate a deterministic SHA-256-derived run identity. Recorder recovers a run across a short process restart only when the intervening gap is **≤180 s** and source/epoch match. Unknown output, manual mode, stale telemetry, stage departure or larger outage CLOSE the old segment; data are never silently interpolated across it. Samples faster than 20 s and timestamp replays are ignored.

The diagnostic store lives in **its own** `/opt/services/rd6018-bot/state/voltage_relaxation.db` SQLite database, fully separate from the production `rd6018.db`, under independent append-only tables:

- `voltage_relaxation_runs`: `run_key`, `segment`, session/battery/profile/stage IDs, first/last verified OFF timestamps, `status` and `signature_json`.
- `voltage_relaxation_samples`: `run_key`, `segment`, `timestamp_s`, elapsed, terminal `battery_voltage_v`, Output `battery_current_a`, external temperature, source age.

## Computation, **not** autonomous diagnosis

After verified continuous data reach each window, the module estimates OLS slope of terminal voltage versus elapsed time:

- `relax_5_15`: between 5 and 15 minutes after the *first proven OFF reading*;
- `relax_15_60`: between 15 and 60 minutes;
- `slope_magnitude_ratio`: late/early absolute slope if the early signal exceeds the 0.1 mV/min numerical floor.

Returned metric fields include `slope_mv_per_min`, `estimated_drop_mv`, and sample count. Five or more samples per window, both endpoints within 90 s, and no internal interval greater than 180 s are required. Metric `insufficient_data` means the evidence is incomplete, **not** low/no stratification. Source resolution is ~0.01 V, so individual sample differences are noisy; linear regression mitigates but does not eliminate quantization error.

The signature cannot determine electrolyte stratification, recovered capacity, or authorize EFB escalation to 17–17.3 V on its own. Correlating it with controlled A·h, temperature, measured battery capacity and ideally electrolyte density is **future offline analysis**, not a runtime threshold. Existing MIX Δ evaluation and 2-hour finish hold stay unchanged.

Example query via the existing SQLite:

```sql
SELECT profile,session_id,continuation,started_at_s,last_at_s,status,
       json_extract(signature_json, '$.relax_5_15.slope_mv_per_min') AS mv_min_5_15,
       json_extract(signature_json, '$.relax_15_60.slope_mv_per_min') AS mv_min_15_60
FROM voltage_relaxation_runs
ORDER BY started_at_s DESC LIMIT 20;
```

## Validation / deployment gates

Software tests cover EFB/Ca/Ca-only qualification, excluded AGM, unknown Output, stale timestamps, temperature loss, noisy/insufficient windows, restart continuity vs outage, session changes, and early SAFE_WAIT completion. **No physical voltage or current commands are part of this module.**

**Real node104 read-only source-shape PASS, 2026-10-15:** production HassClient returned `switch`, `current`, `battery_voltage` and `output_state_code_v2` with `status=ok` and source ages ~0.4–1.7 seconds; physical Output OFF. Standalone unit commissioning must confirm the independent database can be created without altering the production bot or charging state. A real positive SAFE_WAIT capture can only be established on a later naturally occurring authorized charge cycle; no fake session metadata may be injected into production.

The current operator physical test ceiling **15.5 V remains unchanged**. This module does not affect any recipe or use >15.5 V.

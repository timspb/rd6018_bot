# B1031 — optional Native callback phase capture

**Status: offline fake acceptance only. No live Native callback or physical
state was collected.**

The existing D106 observer subscribes once through its D091 read-only collector.
The D091 callback wrapper now forwards `connection_generation` and
`source_client` from the existing `ESPHomeTransport` subscription callback.
Captured generation is included only when actually supplied by that transport;
it is never inferred from a timestamp, HA cache or object ID. D106 normalizes
the optional field without changing the existing OFF proof DTO or serialized
schema.

## Capture API

`tools/node104_native_phase_capture.py` exports:

```python
capture_native_phase(
    records,
    phase_started_monotonic=<phase boundary>,
    captured_at_monotonic=<capture boundary>,
)
```

`records` is an already captured mapping with exactly `output_r18`,
`voltage_v` and `current_a`; each value is an existing D106-style record:

```python
{"value": <typed callback value>, "meta": <Native callback metadata>}
```

The metadata must identify `source="esp_native_api"`, `native_type` and
status `SensorState`/`ok`, the normalized field and actual ESP object ID,
integer `native_key`, `device_id` and original `connection_generation`, plus
the callback's `subscription_timestamp_monotonic`. The helper requires one
device, three distinct keys, one generation, timestamps within the specified
phase interval and freshness no greater than the existing 8 seconds. Result
records retain the source, Native key, device ID, exact generation, original
callback timestamp and monotonic age.

The helper is a pure per-phase projection. Invoke it separately for each phase
from values captured by the existing observer. It does not create a Native
session or subscription, start a task, poll, persist, invoke commands, pair
phases to receipts, or claim causal evidence. It accepts either observed R18
value (0/1); OFF requirements and any causal receipt checks remain with their
existing owners. If generation is missing, boolean, malformed or inconsistent,
capture fails closed.

`ESPHomeTransport.get_entity_state()` was inspected and exposes generation,
key, device, monotonic timestamp, age, source and native type from its keyed
cache. It was not called because this task prohibits network and hardware
access; the optional API consumes already captured callback values. D149 is a
separate phased release-observer router and is not modified or repurposed.

## Evidence

- Focused D091/D106/projector cohort: 74/74 tests PASS on the project venv.
- Five new fake-only tests exercise generation retention, missing identity,
  source/type/timestamp/freshness rejection, device/generation consistency and
  duplicate `SensorInfo` versus colliding `NumberInfo` handling.
- Selected `py_compile` and `git diff --check`: PASS.
- No direct ESP, HA, RD6018, Output, setpoint, firmware, service or deployment
  access. This is not physical acceptance and leaves P3/P8 HOLD unchanged.

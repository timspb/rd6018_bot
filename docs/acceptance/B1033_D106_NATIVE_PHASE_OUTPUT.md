# B1033 — D106 Native phase observation output

**Run ID:** `rd6018-b1033-20261126-r73-d106-phase-observer`
**Starting source HEAD:** `b9b662e7bc3b03fd3b638a2c40c447a9afbd7454`
**Acceptance:** bounded fake/source checks only; no live or physical acceptance.

## Change

`tools/node104_d106_live_observer.py` now accepts `collect_live(phase_observation=True)`, also exposed as the CLI flag `--phase-observation`. The opt-in branch uses the three measurement callbacks already obtained by D106 through D091's existing read-only Native subscription. It adds no client, connection, subscription, task, polling loop, or actuator action. It returns `native_phase_observation` with an explicit `ON` or `OFF` phase label and phase records. It skips the HA fetch, OFF projection, persistent session admission, and OFF proof serialization in this mode.

The default `collect_live()` remains on the existing path. Its `trial_off_proof` construction and serialized shape are unchanged. D091 callback filtering continues to reject supplied stale/foreign connection generations before accepting callback values. The B1031 projector then requires the actual generation, a single device and generation, three distinct SensorInfo keys, the actual ESP object IDs, callbacks within the phase/freshness bounds, and `esp_native_api` provenance. Returned records preserve callback timestamps and report derived monotonic age. HA-only input cannot qualify.

## Test evidence

Using `/home/home-pc/.venvs/pcp-test/bin/python`:

```text
python -m unittest tests.test_b1033_d106_native_phase_observation \
  tests.test_b1031_native_phase_capture \
  tests.test_node104_d106_native_callback_record -v
Ran 16 tests — OK
```

The new six-test module covers observed ON capture and Native identity/generation/timestamp/age, OFF remaining a phase observation, HA-only rejection, cross-generation rejection, missing-generation/stale rejection, and a source-contract check that the default OFF projection remains and the phase branch uses the single existing callback collection without actuator methods. Existing B1031 and D106 callback tests cover keyed SensorInfo identity and callback provenance. `py_compile` and `git diff --check` passed.

An earlier broader 56-test command included the new tests and existing D106 readonly recovery suite. It reported 55 pass and one failed test because the fixture changed a non-authoritative age field rather than its source timestamp. After correcting the fixture, the direct 15-test cohort passed; the 56-test cohort was not repeated.

## Boundary and status

This is not a live capture and makes no P3 Gate 3 or typed receipt linkage claim. No Output, setpoint, lease, firmware, service, node104, ESP, HA, or deployment action occurred. The D151 installed proof source/pin was not modified. D151 and its historical immutable CRLF proof remain the existing installed acceptance basis; the enhanced D091 source is not promoted or presented as D151.

P0–P9 remains 98/103, with three P3 physical checks and two P8 release/physical checks on HOLD. No shared runbook, checkpoint, master plan, or handoff canon was edited; controller reconciliation owns those documents.

## Changed paths

- `tools/node104_d106_live_observer.py`
- `tools/node104_native_phase_capture.py` (adds actual object identity to projected phase records)
- `tests/test_b1033_d106_native_phase_observation.py`
- `docs/acceptance/B1033_D106_NATIVE_PHASE_OUTPUT.md`
- `B1033_REPORT.md`

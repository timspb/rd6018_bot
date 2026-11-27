# B1033 — D106 Native phase observation

**Run:** `rd6018-b1033-20261126-r73-d106-phase-observer`
**Base:** `b9b662e7bc3b03fd3b638a2c40c447a9afbd7454`
**Scope:** source-only, read-only D106 Native observation; no physical/live collection.

Added the opt-in `--phase-observation` mode to `tools/node104_d106_live_observer.py`. It consumes the existing D091 fresh `SensorState` callback set from D106's single ESP connection/subscription and returns a separate `native_phase_observation` payload. It captures R18, measured voltage, and measured current for either observed output state. It does not invoke `project_off`, HA, an actuator API, or a second subscription in this mode. The default `collect_live()` remains the existing OFF-proof path and its return schema is unchanged.

The captured result carries the actual Native device ID, SensorInfo key and object ID, connection generation, original monotonic callback timestamp, and derived age. Missing generation, stale/out-of-phase callbacks, HA-only provenance, and cross-generation records fail closed through the existing B1031 phase projector. ON records are explicitly labeled `phase: ON` and never serialized as `trial_off_proof`.

## Verification

- Project venv focused tests: **16/16 PASS** (`test_b1033_d106_native_phase_observation`, `test_b1031_native_phase_capture`, `test_node104_d106_native_callback_record`). The B1033 source-contract fake also confirms a single fresh callback collector invocation, unchanged default OFF projection path, and no actuator methods in the phase branch.
- Project venv broader D106 observer regression was also run: **56 tests, 1 failed** due to the initial stale-age fixture using a non-authoritative field. The fixture was corrected to move the original timestamp outside freshness; the corrected cohort above passes. The broader 56-test cohort was not rerun after that fixture-only correction.
- `py_compile` for the edited observer, phase capture module, and new test: PASS.
- `git diff --check`: PASS.

No D151 source/pin, D090/D091 proof contract, Output/setpoints, firmware, service, node104, ESP, HA, deployment, GitHub, index, or commit was changed or accessed. This is fake-only software evidence: it does not collect live Native data, link a typed receipt, claim B1020 P3 Gate 3 PASS, or alter P3/P8 HOLD. Existing D151 installed proof remains separate and untouched.

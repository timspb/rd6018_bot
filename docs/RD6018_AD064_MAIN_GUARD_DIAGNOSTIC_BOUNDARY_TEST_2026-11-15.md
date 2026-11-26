# P1-AD064 — MAIN Guard quarantine diagnostic boundary regression
Date: 2026-11-15
Status: ACCEPTED — test-contract correction; no production behavior change.

## Finding

The existing clean production implementation `application/main_guard_runtime.py::_quarantine_reason` deliberately formats only bounded normalized/measurement evidence and does not copy the raw `protection_code` field from `native_age_s` into Application quarantine text. This preserves the current owner boundary: raw R16/protection representation remains in Telemetry/Safety/diagnostics and is not leaked into Application workflow text.

The existing test incorrectly asserted that `protection_code:0.5s` must appear in the Application quarantine reason. That assertion contradicted the current user-approved protection ownership rule.

## Change

Only `tests/test_d109_main_guard_runtime.py` changed:
- replaced the stale positive assertion with `assertNotIn("protection_code", reason)`;
- added a comment explaining the raw protection-code boundary.
No production code, safety behavior, diagnostics source, test fixture semantics, lease behavior, ExecutionPort path, or physical action changed.

## Verification

Windows project `.venv`, Python UTF-8 mode:
- `tests/test_d109_main_guard_runtime.py`
- `tests/test_d109_main_guard_checkpoint.py`
- `tests/test_main_guard_admission.py`
- `tests/test_main_guard_shadow.py`
- `tests/test_main_guard_transaction.py`

Result: **76 passed, 1 deselected, 43 subtests passed** (130 s). The one deselected test creates a symlink; Windows host privilege returned WinError 1314. WSL collection of this cohort is blocked before assertions by missing `python-dotenv`; no dependency was installed or environment modified. The Windows UTF-8 mode resolves the separate cp1251 source-read collection issue.

The initial run exposed the stale protection-code assertion; it was corrected to assert the intended boundary. No test was weakened: the revised assertion now enforces that raw protection codes are not copied into Application quarantine text.

## Repository / safety state

Branch `feature/main-mix-countdown-display`; HEAD `3c692554074b27805419a9b0767133a1c8d78150`. Existing dirty WIP preserved. No reset/clean/stash/checkout/stage/commit/push. No HA/node104/ESP access, firmware, OTA, service restart, hardware action or deployment. Release remains HOLD.

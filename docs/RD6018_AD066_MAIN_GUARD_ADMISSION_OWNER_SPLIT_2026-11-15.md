# P1-AD066 — MAIN Guard admission / canonical session reader owner split
Date: 2026-11-15
Status: ACCEPTED — bounded source-owner split with fake regression.

## Decision

Split the previously mixed responsibility across existing owners only:
- `runtime/charge/strategy/main_guard_admission.py` — **Safety Authority**. It now contains only the read-only MAIN Guard admission contract and its typed result. It validates canonical session identity/recipe, fresh Native electrical evidence, programmed Iset agreement, and the existing independent Safety protection verdict. It never writes a journal or physical output.
- `runtime/charge/persistence.py` — **Sessions & Persistence**. It now owns `read_canonical_session(path)`, the shared read-only canonical session snapshot helper. The helper rejects symlinks/non-files, decodes UTF-8 JSON, accepts only a dict, and returns None for malformed/unavailable input.
- `runtime/production_runtime.py` and `runtime/startup_recovery.py` import the reader from the persistence owner. No wrapper, duplicate helper or new module remains.

## Exact source changes

1. Added `read_canonical_session` to the existing `runtime/charge/persistence.py` beside its canonical session constants and JSON/path imports.
2. Removed the helper and its now-unused `json`/`Path` imports from `runtime/charge/strategy/main_guard_admission.py`; its public export now contains only `MainGuardAdmission` and `admit_main_guard_shadow`.
3. Updated the existing production runtime and startup recovery imports to use `runtime.charge.persistence`.
4. Updated `tests/test_main_guard_admission.py` to import the reader from its persistence owner, use explicit UTF-8 for source inspection, and assert the reader has one persistence owner. Existing tests cover missing, malformed, valid and symlink session snapshots; the symlink case is deselected on this Windows host because creation requires an unavailable privilege.

No session format, age rule, identity rule, Native freshness threshold, protection rule, Iset tolerance, guard admission behavior, recovery sequence, lock, timer, poll cadence, physical command or output behavior changed.

## Why this is a real boundary

Before the change, the Safety admission module also exposed a file-read helper used by startup recovery for restore/reconciliation. That created a file-level owner conflict (Safety admission vs Sessions & Persistence). Moving the 10-line read helper into the existing persistence owner removes the cross-owner helper without creating a facade or new package. The admission function is now a coherent Safety boundary; persistence remains the single owner of canonical session-file reads.

## Verification

Windows project `.venv`, focused cohort:
- `tests/test_main_guard_admission.py`
- `tests/test_d109_main_guard_runtime.py`
- `tests/test_d109_main_guard_checkpoint.py`
- `tests/test_main_guard_shadow.py`
- `tests/test_main_guard_transaction.py`
- `tests/test_restart_restore_ha_composition.py`
- `tests/test_startup_authority_integration.py`

Result: **80 passed, 1 deselected, 43 subtests passed** (151.52 s). The one deselected test requires symlink creation; Windows host privilege returns WinError 1314. WSL collection of this cohort remains blocked before assertions by missing `python-dotenv`; no dependency was installed.

## Repository / safety state

Branch `feature/main-mix-countdown-display`; HEAD remains `3c692554074b27805419a9b0767133a1c8d78150`. Existing WIP preserved. No reset/clean/stash/checkout/stage/commit/push. No HA/node104/ESP/device access, firmware, OTA, service restart, hardware action or deployment. Release remains HOLD.


AD066 final verification correction: the architecture regression `test_canonical_session_reader_has_one_persistence_owner` was added, and source-file reads in that test now specify UTF-8 explicitly. Final Windows project .venv run (without global UTF-8 mode) is **80 passed, 1 deselected, 43 subtests passed** (151.52 s). The deselected case is only the symlink-creation test blocked by Windows host privilege. `py_compile` passed for all five changed Python files; `git diff --check` passed (existing CRLF/LF normalization warnings only).


The final architecture regression in `test_main_guard_admission.py` also asserts that `read_canonical_session` is defined only by the persistence owner and imported by startup recovery from that owner. Source inspection in that test now explicitly uses UTF-8, so this cohort passes without changing the process-wide Python encoding mode.

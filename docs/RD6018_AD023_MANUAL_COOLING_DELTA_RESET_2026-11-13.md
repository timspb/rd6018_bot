# RD6018 AD-023 — unified Manual Delta evidence reset after verified cooling OFF (2026-11-13)

Architectural approval: implement the narrow root-cause repair established by P1-AD022. In `application/manual_cooling_use_case.py`, after `execution_port.disable(...)` has returned verified OFF and the session has transitioned to COOLING, call the existing `self._reset_delta_tracking()` instead of manually resetting only `_delta_confirmations`, `_last_delta_confirmation`, and `finish_hold_started_at`. Keep reset strictly AFTER verified OFF; on disable exception/unverified OFF return FAILED and preserve evidence epoch. Update obsolete comment claiming `_imin/_vmax` are retained as diagnostics during cooling. No new state owner/helper/timer/clock, no change to resume, observer, Delta algorithm, persistence schema, ExecutionPort or hardware behavior.

Exact minimal edit allowlist:
1. application/manual_cooling_use_case.py
2. tests/test_modularization_manual_lifecycle_contract.py
Do not edit other files. In particular AD021 untracked test modules are pre-existing WIP and must not be attributed to AD021 or modified in AD023. If an unexpected dependency requires expansion, STOP and report.

Tests: extend existing verified cooling test to seed/assert `_imin`, `_vmax`, `_delta_confirmations`, `_last_delta_confirmation`, and `finish_hold_started_at` reset; ensure denied/unverified OFF preserves all these fields; retain existing successful resume and start reset tests. Fake ExecutionPort only; no device/HA. Run focused lifecycle module, then full 13-module Manual Windows `.venv` cohort, `py_compile`, `git diff --check`, verify exact two-file allowlist. No stage/commit/push/reset; preserve dirty WIP. This closes the specific AD021 contract mismatch, not physical acceptance. Release/node104 HOLD.

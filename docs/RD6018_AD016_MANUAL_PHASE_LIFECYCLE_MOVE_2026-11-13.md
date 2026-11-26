# RD6018 AD-016 — Manual MAIN→MIX lifecycle ownership relocation (2026-11-13)

Architectural decision: APPROVED as one bounded source-level vertical slice, based on P1-AD015 report. Move the existing pure Manual MAIN evidence lifecycle from Application to existing Charge Strategy department. This is a responsibility relocation, not a new parallel policy or execution path.

Canonical new owner: runtime/charge/strategy/manual_phase_lifecycle.py

Allowed source/test files:
1. NEW runtime/charge/strategy/manual_phase_lifecycle.py — move exact existing ManualPhaseDecision DTO and ManualPhaseLifecycle implementation, preserving API/semantics.
2. application/manual_phase_lifecycle.py — remove old implementation; do not retain duplicate or compatibility wrapper.
3. manual_mode.py — update import only; retain the one existing self.phase_lifecycle = ManualPhaseLifecycle() instance and all existing manager delegates/mirror fields.
4. application/manual_execution_boundary.py — update decision type import only; preserve same identity check and ExecutionPort.apply_intent route.
5. NEW tests/test_modularization_manual_phase_lifecycle.py — fake-only behavioral contract.
6. tests/test_workstream113b_manual_mode_boundary.py — only update direct import if required; preserve semantic assertions.

No other files may change. Exclude Manual use cases, manual_phase_evidence.py, observer, Delta, persistence, profile/config, ExecutionPort, composition, physical adapter, owner registry, docs, and runtime hardware. If another consumer or required dependency is discovered, STOP and report for architect review; do not widen allowlist.

Preserved invariants: exactly one lifecycle object on ManualSessionManager; same state/lifetime; same evaluate_main signature/return and fields confirmations, hold_started_at, last_confirmation_at, last_decision, reset(); injected now only; no new clock/task/timer, I/O, persistence or HA dependency; ExecutionIntent is data only; existing ManualExecutionBoundary identity check and same application-scoped ExecutionPort lock/guarded apply_intent/readback unchanged; event/order/session mutation and MAIN→MIX transition apply-before-mutate unchanged; no change to restart/interrupted semantics, START/STOP, cooling/resume, supervisor failure/OFF, observer or Delta.

Tests: parity contract from P1-AD015: eligibility rejection, CV gate, confirmation interval boundary, hold boundary, exact decision payload and reset. Fake-only boundary test proves identity passed to unchanged port adapter and missing identity prevents call. Existing Manual focused regression cohort and acceptance command from P1-AD015 must all pass. Do not weaken source-text/AST tests; update only direct import if necessary.

Approved source architecture only; not production binding, physical behavior, node104 or release acceptance. Re-read HEAD/dirty status; do not reset/stage/commit/push. Full P0–P9 and physical release HOLD.

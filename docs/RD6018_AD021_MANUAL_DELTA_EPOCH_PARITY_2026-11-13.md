# RD6018 AD-021 — Manual Delta epoch/restart fake-only acceptance contract (2026-11-13)

Architect decision: approve one strictly NON-ACTUATING test-only parity slice, based on source audit P1-AD020. Manual Delta is intentionally Manual-only. D062 adopted-MIX has separate epoch and monotonic clocks. Do not merge them, migrate the state, create a second timer or change production code.

Exact edit allowlist:
- tests/test_modularization_manual_delta_contract.py
- tests/test_modularization_manual_lifecycle_contract.py
- tests/test_modularization_manual_observer_contract.py
No new files outside the Codex launcher task/report. Preserve all existing test assertions, fixtures and source. If a production defect is discovered, STOP and report; the production code is not authorized to change in this step.

Required fake parity: reset CV Imin / CC Vmax and _delta_confirmations/_last_delta_confirmation/finish_hold_started_at on explicit new Manual start, verified cooling OFF and verified resume; interval boundary and backward/equal provided now cannot synthesize confirmation; session restart with persisted non-null MIX hold anchor transitions to INTERRUPTED with no automatic Output ON or observer stop, while new authorized start clears old epoch; finite U/I gate before MIX hold and Delta, unknown regulation inhibits new Delta but established hold may expire; Delta confirmation starts hold and persists, does not OFF on that cycle; expiry delegates to same stop and denied OFF must not claim verified stopped state; inclusive boundary 7200s/profile and blanking 120s/confirmation spacing. Only assert stale metadata rejection if current Manual caller actually provides this policy; otherwise explicitly record the gap rather than introduce it.

Test in memory/temp files only, fake ExecutionPort/Hass; no devices, network, HA/ESP/Modbus. No new session writer or polling. Full 13-module Manual Windows .venv cohort and git diff --check are required for acceptance; not hardware proof.

Working owner registry remains 499 production modules/26 approved primary/473 pending. No Git staging/commit/push/reset and node104 release HOLD. After acceptance update four mandatory runbooks.

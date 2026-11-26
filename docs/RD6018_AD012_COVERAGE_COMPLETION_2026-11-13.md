# RD6018 AD-012 — Architecture decision: complete P1 working-set source coverage (2026-11-13)

Architect APPROVES source-coverage additions, NOT primary owner assignments or module migrations. AD011 diagnostic found 18 previously unregistered, currently untracked-at-HEAD production or production-package Python paths. Preserve all original 481 AD010 rows/columns, 21 approved owner assignments, legacy final_owner empty. Add exactly 18 NEW rows to additive AD012 working-set sidecar, with explicit provenance untracked_at_HEAD and owner status UNAPPROVED. Result required: **499 unique working-set paths, 21 approved, 478 unapproved**. Do not modify original AD010, AD008, AD006 or historical 478 inventory. No automatic owner assignment by filename.

Exact 18 paths:
- application/manual_cooling_use_case.py
- application/manual_mix_transition_use_case.py
- application/manual_observer_use_case.py
- application/manual_phase_evidence.py
- application/manual_start_use_case.py
- application/manual_stop_use_case.py
- application/manual_supervisor_use_case.py
- application/operator_pause_use_case.py
- runtime/charge/evidence/adopted_mix_finish_hold_decision.py
- runtime/charge/evidence/adopted_mix_sample_decision.py
- runtime/charge/evidence/adopted_mix_source_timestamp.py
- runtime/charge/evidence/manual_delta.py
- runtime/charge/restore_admission.py
- runtime/charge/restore_finalization.py
- runtime/charge/restore_projection.py
- runtime/charge/strategy/adopted_mix_admission.py
- runtime/operator/pause_state.py
- runtime/operator/__init__.py

Evidence: AD011 full coverage report + CSV, git untracked status and static source consumers. This includes one package file with no observed inbound source import, but currently its module body re-exports OperatorOffConditions. All additions are source coverage only; no active runtime claim from mere import. New rows should retain data-supported consumer/source references where available and flag review where not; no fake original candidate.

AD012 requires deterministic fail-closed generator + independent validation: exact 499 paths, 481 original row/field values byte-for-field, 18 exact new paths, no duplicates, 21 approvals unchanged, 478 pending, no stale misleading total, no new physical command owners and no altered runtime. Preserve source files, no Git add/commit/push, no node104/ESP/HA/hardware. Full release HOLD.

# RD6018 AD-144 — Manual MAIN-tail decision owner and phase-evidence adapter

Date: 2026-11-16  
Status: **ACCEPTED — source/fake only; no physical acceptance**

## Decision

Approve `application/manual_phase_evidence.py` as the Application adapter for Manual MAIN/MIX phase evidence. It may normalize the current ExecutionPort live sample, apply request/session eligibility gates, delegate decisions to the existing domain owners, map accepted decisions to existing Manual reason strings, and preserve existing HMI projection/logging. It must not own the MAIN-tail threshold policy or profile-based phase lifecycle.

The decision owners are:
- **Charge Strategy:** `runtime/charge/strategy/manual_phase_lifecycle.py` owns profile-based MAIN→MIX evidence lifecycle and MIX finish-hold elapsed decision.
- **Manual Charge Program:** `runtime/charge/programs/manual.py` owns the profile-less Manual MAIN CV tail stop predicate and existing configured Manual stop predicates.
- **First Stage Evidence variables:** `runtime/charge/evidence/first_stage_variables.py` owns the near-target voltage margin and fallback MAIN tail-current threshold.
- **ManualSessionManager:** owns session state, persisted schema and HMI projection fields; `main_min_confirmations` / `main_min_hold_started_at` remain projections of the one existing `phase_lifecycle` object.
- **Application adapter:** owns sample normalization/eligibility, orchestration and reason mapping only.

## Why this boundary

The existing application helper combined telemetry normalization with one profile-less policy expression:
`self._imin is None or current <= self.main_tail_current_threshold_a`.
The profile path already delegates to `ManualPhaseLifecycle.evaluate_main()`; the MIX hold path already delegates to `manual_mix_finish_hold_complete()` under AD019. Keeping the profile-less predicate in Application left one of the Manual MAIN stop decisions outside the Manual Program owner.

The Manual runtime derives a chemistry/capacity-specific tail threshold from `runtime.charge.evidence.first_stage.tail_current_threshold_a()`; when battery identity/record is unavailable it uses the existing 0.30 A fallback. Both the formula and fallback belong to First Stage Evidence. The 0.20 V near-target margin already has a typed owner there as `NEAR_TARGET_MARGIN_V`. Reuse these existing owners; do not create a new variables module or another lifecycle object.

## Approved minimal changes

1. Add `MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A` VariableSpec (default 0.30 A, key `charge.evidence.first_stage.manual_default_main_tail_current_a`) to existing `first_stage_variables.py`; preserve the existing float constant in `manual_mode.py` as a compatibility projection of its default.
2. Add pure `manual_main_tail_reached(imin, current_a, threshold_a)` to existing `runtime/charge/programs/manual.py`; preserve the exact legacy predicate and reason mapping.
3. Replace the inline predicate in `application/manual_phase_evidence.py` with a call to the Manual Program owner.
4. Replace duplicated 0.20 V literals in `application/manual_phase_evidence.py` and `ManualPhaseLifecycle.evaluate_main()` with the existing `NEAR_TARGET_MARGIN_V.default`.
5. Add regression coverage for the fallback variable, Manual Program predicate, adapter delegation, profile path, exact near-target boundary and existing MAIN/MIX lifecycle contract.

No new package, manager, timer, clock, evidence state, persistence schema, ExecutionPort, physical adapter, or alternate MAIN→MIX path.

## Compatibility and exclusions

- Preserve the profile-less predicate exactly: `imin is None OR current_a <= threshold_a`.
- Preserve the exact reason `manual_main_cv_imin`.
- Preserve profile-based `ManualPhaseLifecycle.evaluate_main()`, its one stateful object, confirmation/hold timing, decision payload and ExecutionPort identity boundary.
- Preserve `manual_main_to_mix`, apply-before-mutate ordering, and existing MIX hold reason/logging.
- Preserve the current 0.30 A fallback and 0.20 V near-target defaults; no charging behavior change.
- Do not change Manual Delta sampling/state/epochs; it remains AD145.
- Do not change AD016/AD019/AD021/AD023 accepted semantics.
- Do not modify owner registry sidecars; reconcile AD142–AD144 in a deliberate later registry refresh.

## Test evidence required

Focused parity tests must prove:
- the only AST differences in the old MAIN-tail body are the approved near-target VariableSpec reference and the delegated Manual Program predicate;
- profile-less cases (missing Imin, current at/below threshold, current above threshold) preserve exact result;
- profile-based MAIN lifecycle and decision payload remain unchanged;
- near-target comparison remains inclusive at target minus 0.20 V;
- the application adapter does not contain the profile-less threshold expression;
- the existing Manual/Operator Pause regression cohort remains passing.

Source/fake only; no HA/ESP Native, node104, firmware, OTA, service, hardware or physical charge action.

## Safety and repository

Branch `feature/main-mix-countdown-display`; preserve current HEAD and all pre-existing WIP. No stage/commit/push/reset/checkout/stash/clean. 900-second Edge Safety Lease unchanged. Production/release/physical acceptance remain HOLD.


## Implementation and acceptance evidence

Implemented the approved scope:
- Added typed `MANUAL_DEFAULT_MAIN_TAIL_CURRENT_A` VariableSpec to `first_stage_variables.py` (0.30 A, CONFIG_FILE / RESTART_REQUIRED); `manual_mode.py` retains its float constant as a compatibility projection of that spec.
- Added pure `manual_main_tail_reached()` to the existing Manual Charge Program owner and delegated the profile-less predicate from the Application adapter. The predicate remains exactly `imin is None OR current_a <= threshold_a`; reason remains `manual_main_cv_imin`.
- Reused `NEAR_TARGET_MARGIN_V.default` in both Application request eligibility and Strategy profile eligibility; default remains 0.20 V.
- Updated the source-parity contract to normalize only those two explicitly approved owner relocations. Added direct Manual Program predicate/fallback variable tests and inclusive 0.20 V boundary coverage.
- Updated the Delta characterization fixture to obtain the default threshold from the canonical VariableSpec rather than AST-evaluating a removed monolith literal.

Final Windows project `.venv` acceptance: **212 passed, 45 subtests passed across 29 modules** covering AD143/AD144 Manual observer/evidence/Delta/lifecycle/runtime/store/use-cases, Operator Pause, D072 START, first-stage evidence, Manual Program/profile/start route and workstream113b boundary. `py_compile` PASS for all eight slice files. Trailing whitespace scan: 0. Scoped `git diff --check`: PASS.

SHA-256:
- `runtime/charge/evidence/first_stage_variables.py`: `4CB1057263B6670D3CFF736ACFE30F7694CF9AB7A8DB8927797200F00555EE1D`
- `runtime/charge/programs/manual.py`: `22F990DD8340A9E75E12D9A75613FADB0F820C61D7CE5ADC0EB6F55DA8F0ACF4`
- `runtime/charge/strategy/manual_phase_lifecycle.py`: `53B7D2F809ED581A25F10DCBA9AA454CEC3AA399F523467B75506C35F65B400D`
- `application/manual_phase_evidence.py`: `634DF60EE2F9F623D5A10DC24708DB38E03B2860C273CC310E419E02BCD6BCCA`
- `manual_mode.py`: `F6BFEA4E63B7AF9E63FB0BB3BD7B36D1B580E691509105E8D241BE0D841C33DF`
- `tests/test_modularization_manual_phase_evidence.py`: `AE4C43319A992D55782216245015AE8A2C7217F9BB8AA78CD322C43271DACD5C`
- `tests/test_modularization_manual_phase_lifecycle.py`: `8A182C90A3C53EAD13E80629823C5059E64B767C7980E673687E4CAE87DD056A`
- `tests/test_modularization_manual_delta_contract.py`: `2EB3E170C7CCFCA56EC8E39C93495372910902202A2B74192926259052A357ED`

Repository: branch `feature/main-mix-countdown-display`, HEAD `3c692554074b27805419a9b0767133a1c8d78150` unchanged, staged=0, 468 total status entries (all existing WIP preserved). Three paths in this slice are tracked modifications; five are existing untracked modularization WIP. No cleanup or Git history operation. Root charge/manual/pause/quarantine runtime artifacts absent after tests.

No Codex run was launched because other WSL Codex CLI jobs were already active in separate projects. Own-chat R7.2 route remains enabled with last_ack=null; no event/ACK claimed. node104 not queried or touched; no HA/ESP Native/firmware/OTA/service/hardware/RD6018 Output/physical charge action. 900-second Edge Safety Lease unchanged. Production/release/physical acceptance remain HOLD.

AD144 is accepted as source/architecture only. Owner registry sidecars remain unchanged; AD142–AD144 are to be reconciled in the next deliberate owner-registry refresh.

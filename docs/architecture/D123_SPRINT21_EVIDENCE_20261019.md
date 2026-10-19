# D123 Sprint 21 — MIX evidence/read-model mirror ownership

Date: 2026-10-19. Exact starting HEAD: `15f1446cda978756de6f28cc95c110c995111add`.

Source-only change in the existing WSL2 workspace. No node104, ESP Native API, HA, firmware, service, deployment, GitHub, release marker, physical output or external system was accessed or changed.

## Bounded ownership cut

The active MIX authority path previously copied analyzer metrics directly into the controller dashboard/evidence mirrors: CV updated `i_min_recorded` and CC updated `v_max_recorded`. Sprint 21 moves only those mirror decisions and writes behind `runtime.charge.evidence.mix_observation`.

`build_mix_evidence_mirror` returns a frozen value describing which mirrors may be updated. `apply_mix_evidence_mirror` performs the two existing state writes. CV and CC remain independent, and a missing metric leaves the previous value unchanged. The controller has one builder/application route and no longer contains the inline assignments.

MIX decision logic, finish-hold ownership, completion/final SAFE_WAIT effects, targets, protection limits, recipes, persistence, session schema, Guard, 900 s lease, execution routing and physical writers are unchanged.

## Changed files

- `charge_controller.py` — delegates MIX read-model/evidence mirror updates.
- `runtime/charge/evidence/mix_observation.py` — frozen mirror value and owner.
- `tests/test_d123_p3_mix_evidence_mirror.py` — CV/CC parity, missing-metric and static one-caller/no-physical-writer guards.
- D123 checklist / owner map — Sprint 21 ownership and remaining gates.

## Verification

Focused MIX set: **17 PASS**.

Canonical full offline discovery with the existing Python 3.12 venv and a synthetic token: **2,406 tests, 3 skipped, PASS**.

`python -m compileall -q .`: PASS. `git diff --check`: PASS.

The requested `/tmp/rd6018-d109-venv/bin/python` remains absent; no replacement environment or dependency was installed. This is source/software evidence only, not deployment or physical acceptance.

## Remaining gate

P3 still retains MIX completion-evidence logging, `_apply_authoritative_decision` dispatch/orchestration, Storage/DONE and Manual integration, and eventual application-owned session tick. P2 Guard restore admission remains fail-closed/deferred. P4/P5 and physical acceptance remain open.

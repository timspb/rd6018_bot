# D123 Sprint 51 — P4 recipe target policy ownership

Status: source-only P4 slice from exact clean baseline
`af8521095f6394c41f6ff96abfa11b220f4df7fc`, branch
`codex/d118-start-lease-repair-20261019`. No live node104, ESP, HA, firmware,
service, deployment, GitHub, or physical access was used.

## Cut and exact ownership change

`application.production_target_policy` now owns two cohesive operations:

- resolving the recipe envelope from the existing production profile, capacity,
  battery ID, intent, and condition (including the existing Custom bypass);
- applying the envelope voltage ceiling and MAIN/HV current ceiling to a target.

`ProductionChargeController` remains the only production session/state host. Its
existing target adapters supply their already-selected targets and host context
to the policy owner. Restored target clamping uses the same policy functions.
The controller declarations `_recipe_envelope`, `_bound_target`, and
`_current_stage_is_hv` were removed; `_bound_recipe_target` is the thin
integration point for normal target selectors.

Before: `production_controller.py` had 24 method declarations and 736 lines.
After: it has 22 method declarations and 713 lines (-2 declarations, -23 lines);
the new application owner is 42 lines. This is an ownership move, not a claim
that the base facade is removed. `ProductionChargeController` still inherits
`ManagedChargeController`, and the runtime still constructs exactly one
production host. The existing FSM/session state remains singular.

## Behavior and excluded boundaries

Target selection, thermal compensation, voltage/current ceilings, Custom
authority, persisted intent/default migration, restored-target bounds, runtime
signal and finish-state behavior are unchanged. No charge strategy, recipe
value, 900 s lease, safety, OVP/OCP, ESP priority, Manual behavior, persistence
schema, or MAIN Guard policy changed. MAIN Guard restore admission remains
fail-closed/deferred; this cut does not modify or reorder restore admission.

Static and behavioral checks in `tests/test_d123_p4_recipe_target_policy.py`
prove that the three policy methods are absent from the controller facade,
the new application owner supplies the operations, EFB Diagnostic clamps to
its existing voltage/current limits, Custom bypass is unchanged, and runtime
construction still has one `ProductionChargeController` constructor and no
second `ManagedChargeController` host.

## Verification

- Focused target, production composition, controller restore, session binding,
  and terminal Guard set: **58 PASS**.
- Full Python 3.12 offline unittest discovery with synthetic
  `TG_TOKEN=123456789:d123-sprint51`: **2,448 tests, 3 skipped, 0 failures**.
- `/home/home-pc/rd6018-v3-deploy/.venv/bin/python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- No dependencies installed.

## Remaining blockers to remove inheritance

The inheritance still supplies the one live host's state and roughly 53 base
lifecycle/state/session/target methods. A mechanical base change would lose the
single canonical state host and disturb START/reset/stop, session lifecycle,
ordinary restore sequencing, execution integration, and production extension
hooks. The remaining coherent work must migrate that state/lifecycle contract
into the existing application/session owners without creating a second state
object. Ordinary restore still hands the canonical raw document to both base
restore reconstruction and production extensions. MAIN Guard restore admission
has no canonical owner-wide pre-ON reconciliation and must stay fail-closed;
that authority-bearing admission must be separately resolved before moving its
restore consumer. Production cooling-pause and runtime-signal/finish extensions
also still mutate/read host-owned state and persisted extension fields and need
an explicit single-owner/session lifecycle design before extraction. This sprint
does not claim a path through those blockers.

## Commit gate

Commit SHA and post-commit clean-worktree result are recorded in the sprint
completion message after all gates pass.

# RD6018 operator buttons ? single editable rule set

The available **Telegram control buttons** are selected by the application rule
directory `application/operator_button_rules/`. Keep each rule short and
focused. This is NOT a new control plane: safety, authorization, and actuator
effects remain exclusively with the existing command handlers.

| Edit this file | When |
| --- | --- |
| `session.py` | Running AUTO/Manual, pause/resume, STORAGE, interrupted Manual |
| `external.py` | HANDS_OFF Output ON/OFF, adopted or interrupted MIX |
| `snapshot.py` | Generic sanitized snapshot states: IDLE, CHARGING, HANDS_OFF, FAULT |
| `selection.py` | Which existing rule applies to the supplied read-only state |
| `common.py` | Conversion to the existing `OperatorActionsView` read model |
| `runtime/ui/labels/operator_actions.py` | Operator-visible text and existing callback IDs |

The canonical entry points are `actions_for_hmi(state, paused=...)` and
`actions_for_snapshot(snapshot)`. `OperatorSnapshotProvider` calls these,
while the existing `build_operator_keyboard` calls the same selector when
legacy callers do not supply a view. It **does not** maintain a competing
button-eligibility table. Both render through `_keyboard_from_actions`.

Interrupted Manual is identified through the explicit read-only
`OperatorHmiState.manual_interrupted` field. Do not parse Russian progress
text or derive a separate persisted state. The original
`v2_manual_reauthorize` and `v2_manual_discard` handlers still own
execution and safety/readback validation.

Existing real dashboard, graph, and /start fallback call sites retain their
public signatures. No additional timer, polling task, Telegram publisher, or
physical authorization is introduced. Do not change the installed node104
D144 slot14 baseline without explicit deployment approval.

Acceptance for the source-only refactor on 2026-11-07:
296/296 selected UI, dashboard, graph, recovery and ownership tests PASS,
9 subtests PASS; `compileall` and `git diff --check` PASS. One separately
identified `test_operator_navigation_expired_callback.py` assertion fails
**also on unchanged HEAD 42880af** under the same Windows test environment;
it was independently run in a detached temporary Git worktree and is not
reported as passing. This is an existing callback-navigation defect, not
evidence of production failure or acceptance of actual recovery.

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

## Snapshot identity continuity (2026-11-07)

An interrupted Manual is an **IDLE** operator snapshot with the explicit
read-only `manual_interrupted=True` field. The canonical HMI builder supplies
that field once, `OperatorSnapshotProvider` preserves it, and the same
`session.interrupted_manual()` rule supplies the actions whether Telegram
starts with a full HMI state or a sanitized snapshot. The snapshot must never
infer it by searching the Russian progress text or by making another HA read.
`snapshot_from_mapping` accepts the field for offline/serialized readers.
This change is presentation only; the existing Manual authorization/discard
handlers retain all safety checks and output authority.

The `operator_done` navigation handler acknowledges Telegram callbacks;
`PanelLastMiddleware` is still the *sole* owner of L2 refresh. The old test
that demanded independent refresh/delete from that handler was updated to the
existing single-owner behavior, including expired Telegram callback cases.

## Graph / L2 composition (2026-11-07)

`operator_dashboard._composed_operator_rows` is the one small composition
helper for both text-panel and graph-panel RD controls. It invokes the
**already-installed** `operator_hmi.build_operator_keyboard` exactly once,
preserving the existing PB ownership, managed adoption and MIX eligibility
wrappers. Those wrappers augment the common application action rules; they
are not replaced with a second physical authority. The existing release
button filter is applied during managed charging for the normal panel and
unconditionally for the active graph workspace, preserving prior behavior.

`OperatorSnapshotProvider.get_operator_actions(snapshot=snapshot)` now
receives the same read-only snapshot already used to render the associated
panel text in all three graph/dashboard refresh paths. This avoids a second
read of runtime telemetry while choosing action capabilities.

Acceptance: 306 selected UI/graph/operator/recovery tests PASS and 27 subtests
PASS with Windows PYTHONUTF8=1; compileall and git diff --check PASS. A focused
composition regression asserts managed-charge release filtering without
hiding the control in unrelated idle states. No new Telegram publisher,
handler, rule engine, control channel, or hardware operation.

## HMI display edit locations

The pure immutable read model and enums are in
`runtime/ui/components/hmi_state.py`. The compact text formatting
(main-stage label, transitions, display of Imin/Vmax and finish evidence)
is in `runtime/ui/components/hmi_compact.py`; these are not charge policy
or safety authority. Edit compact transition truncation and heading widths
in `runtime/ui/hmi_layout_config.py`. Keep all action eligibility edits in
`application/operator_button_rules/` and action captions in
`runtime/ui/labels/operator_actions.py`; do not add policy or runtime
ownership to the presentation modules.

## Detail/diagnostic editing locations
For operator detail text, edit `runtime/ui/components/hmi_operator_details.py`;
for technical diagnostic text, edit `runtime/ui/components/hmi_service_details.py`.
Single MIX observer state projection belongs to `runtime/ui/components/hmi_observer_runtime.py`.
These are read-only formatters, not charge control or Telegram publishers.

## Manual and unowned state display edit locations
Manual active/interrupted read-only UI projections: runtime/ui/components/hmi_manual_states.py. HANDS_OFF, unowned Output ON containment and idle read-only UI projections: runtime/ui/components/hmi_unmanaged_states.py. The runtime owns charging and session state; application/operator_button_rules controls available actions. Do not put actuator calls or an independent button eligibility table in either presenter.

## Panel and keyboard presentation locations
The compact panel text is rendered only in runtime/ui/components/hmi_panel_text.py. The application-approved actions are laid out into Telegram button rows only in runtime/ui/components/hmi_action_keyboard.py. operator_hmi.py reexports the functions for current callers and retains the installed publishers and ownership wrappers. Change action availability in application/operator_button_rules and action captions in runtime/ui/labels/operator_actions.py, never add a parallel eligibility or publisher in the renderers.

## Navigation presentation owners
Graph/back/more keyboard rows are in runtime/ui/components/hmi_navigation_keyboards.py. Keyboard-only compatibility state projection is in runtime/ui/components/hmi_compat_dashboard_state.py. Actual eligibility stays in application/operator_button_rules; Telegram publishing and callback ownership remain in existing installed handlers.

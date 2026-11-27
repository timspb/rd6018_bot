# V3 Modular UI Architecture

Status: **required architecture**, not optional cleanup.

The UI has historically been the easiest layer to lose during runtime
refactors. V3 therefore treats UI screens, buttons, navigation and operator
actions as versioned modules with static contracts.

## 1. Layer boundary

```text
Application Read Model
        |
        v
OperatorSnapshot / ViewModel
        |
        v
ScreenSpec
  +-- text/components
  +-- ButtonSpec[]
        |
        v
Telegram renderer/transport
```

Actions travel in the opposite direction:

```text
ButtonSpec.action
        -> UIAction
        -> OperatorIntent
        -> Application service
```

UI never calls controller, safety internals, HA, ESPHome or RD6018.

## 2. Target structure

```text
runtime/ui/
  models.py
  actions.py
  buttons.py
  variables.py
  routing/
    registry.py
    state_router.py
  screens/
    home/
    charging/
    batteries/
    manual/
    diagnostics/
    recovery/
    mix/
    settings/
    service/
    graph/
  components/
    telemetry.py
    safety.py
    progress.py
    confirmations.py
    pagination.py
  telegram/
    renderer.py
    adapter.py
    transport.py
```

The exact filenames may evolve, but ownership boundaries may not collapse back
into a monolithic handler module.

## 3. Buttons

All V3 buttons are declarative `ButtonSpec` objects. A button owns:

- stable id;
- display label key/text;
- UI action id;
- optional confirmation requirement;
- optional visibility capability;
- navigation target where applicable.

A screen composes buttons. It does not implement the action.

No new V3 code outside the UI button/renderer layer may construct
`InlineKeyboardButton` or assign raw Telegram `callback_data`.

## 4. Navigation

Navigation uses stable `ScreenId` values. It must not depend on unrelated
historical callback names such as multiple variants of "back", "home" or
"dashboard".

Adding a future screen must require only:

1. its screen module;
2. its button declarations;
3. registration in UI routing;
4. optional application intent handler when it introduces a new use case.

It must not require editing the charge FSM or runtime monolith.

## 5. State and available actions

The application/read-model layer determines what actions are available for the
current state. UI renders those capabilities.

The idle charge button is a read-only navigation capability: it opens the
charge-mode/profile workspace and must remain visible even when the current
safety snapshot would reject a physical start. Physical start is independently
re-authorized by the current preflight/execution boundary; UI visibility never
grants Output ON authority. Home text and idle actions must be derived from the
same operator snapshot so a telemetry refresh race cannot produce a normal
status with a fault-only keyboard.

A button must never remain enabled merely because an old Telegram message
contains its callback. The routed action is re-authorized against current state.

## 6. UI variables

UI-owned configurable values live in `runtime/ui/variables.py` or a specific
component/screen `variables.py` when ownership is narrower.

Examples:

- refresh cadence;
- graph window;
- pagination size;
- confirmation lifetime;
- maximum journal rows rendered.

Each variable uses the common metadata contract from the modular architecture.
Charge/safety values are forbidden in UI variable files.

## 7. Forbidden imports/calls

Canonical V3 UI must not import:

- `runtime.v2_runtime`;
- `charge_logic` / historical ChargeController;
- `hass_api`;
- ESPHome/HA physical transports;
- safety/output executors;
- database mutation APIs.

Canonical V3 UI must not call:

- `turn_on`, `turn_off`;
- `set_voltage`, `set_current`, `set_ovp`, `set_ocp`;
- session mutation or charge-stage transition methods.

Telegram is a renderer/transport adapter only.

## 8. Migration

The existing V1/V2 UI is a behavior/reference source while screens move one at
a time. A migrated screen receives a canonical ViewModel and emits canonical
actions. After parity, its old callback/rendering path is removed rather than
kept as a fallback.

### Telegram battery selection ownership

The existing `runtime/ui/telegram/battery_selection.py` owns battery-selection
callback token encoding and row presentation together with its process-local
page/selected-record maps, callback resolution and selection read function.
Registry lookup belongs to this selection workflow owner. `production_bot_ui`
may retain direct compatibility exports, but those exports reference the same
maps/functions; it does not create a second cache or battery-selection policy.
The installed Telegram handler retains chat authorization, callback
acknowledgment, prompt rendering and selection ordering. The selected value is
the registry's original `BatteryRecord` object.

### Telegram pending charge-program wizard

The existing `runtime/ui/telegram/charge.py` owns the process-local pending
charge-program wizard DTO (`PendingStart`), profile/intent/START maps, the
selected-program display projection, and user-scoped pending-state clearing.
`production_bot_ui` retains direct compatibility imports of those exact class,
map, and function objects while its installed handlers continue to sequence
profile, Ah, intent, recipe/native-recipe choice, and START callbacks. The
accepted battery START route uses the same clear function after the
existing route accepts and START feedback is delivered. Rejection, submission
exceptions, and feedback-delivery failures retain pending state. Clearing does not remove the selected battery or another user's state;
battery selection remains owned by `battery_selection.py`.

This is process-local UI state only: it adds no persistence or second state
source and carries no charge-transition or physical authority. The existing
`app.awaiting_ah` marker remains the text-input routing selector and is cleared
alongside wizard entries by the existing helper. Whole-file
ownership for `production_bot_ui.py` remains unresolved under the P1 owner
review. See `.recipe-studio-local/REPORT_RD6018_P6_PENDING_PROGRAM_BATCH15_20261119.md`;
native Windows test acceptance is pending.

## 9. Completion gate

UI migration is complete when a future button or screen can be added without
touching `runtime/v2_runtime.py`, `charge_logic.py`, controller classes,
physical execution or safety modules.

## Non-negotiable modularity and configuration canon (2026-11-07)

**No new monoliths.** This applies to all RD6018 changes, including operator HMI, charging algorithms, recovery, telemetry, logging, and release tooling. An existing oversized file is not a license to add another feature branch to it.

- One module owns each capability, state transition, clock, renderer, configuration value, and side effect. Separate read models, pure policy/formatting, orchestration, Telegram adapter, hardware execution, and persistence. Composition wires them; it must not reimplement their rules.
- Every user-tunable duration, threshold, limit, recipe parameter, choice, and policy belongs in the owning module's declared typed `variables.py` / `config.py` (or the canonical existing recipe/spec registry). Define units, default, range, provenance, override policy, and change effect. All consumers read that same definition; no scattered literals, shadow settings, duplicate copies, or hidden environment overrides.
- Presentational countdowns **derive** from the existing SignalAnalyzer/MAIN authority timestamps and configured hold duration. They never establish their own timer, storage, charge transition authority, or additional polling process. Different chemistry/intent must not be inferred from ad-hoc UI constants.
- Preserve exactly one Telegram panel lifecycle owner, one 60-second refresh task, and in-place edits. New UI features belong in focused read-model/presenter/component modules; the Telegram adapter stays transport-only. Do not expand `operator_hmi.py`, `runtime/production_runtime.py`, or `bot.py` with new cross-layer policy.
- Before each change: identify existing canonical owner and config source, perform the smallest source modification that implements the requirement, and remove superseded code rather than adding shims. Do not construct a parallel abstraction, extra proof/authorization, new service, duplicate observer, or alternative rollback path.
- Acceptance: focused module tests + existing architecture/UI regressions + actual entrypoint behavior where relevant. Record evidence and exact SHA in the runbook. Keep the deployed known-good baseline untouched until an explicit safe D145/D144 installation is authorized; never confuse source acceptance with live hardware/UI acceptance.
- If requested work needs a new setting or subsystem, extend the original semantic owner rather than opening an independent control plane. Reject any design that makes two modules authoritative for the same state.


## 2026-11-19 — independent P6 battery-selection owner batch-13 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p6-battery-intent-ui-owners-luna-20261119-13` exited 0; R7.2 own-chat event `013ab53022764942a3933388d590612d` ACK confirmed (attempt=1). Source/fake only.
- Existing `runtime/ui/telegram/battery_selection.py` now owns process-local battery page/selected-record maps, durable-token/legacy-index resolver and selection lookup. `production_bot_ui` retains direct alias objects and registered callback order. Independent review fixed real import regression: `list_batteries` belongs to `battery_catalog`, not `battery_registry`. Two legacy test fixtures now patch the actual current owner without weakening expected behavior.
- Independent native Windows project venv expanded twelve-module callback/UI/battery/recipe cohort: **127 PASS + 71 subtests PASS**, exit=0. The earlier host runs detected import regression and stale monkeypatch fixtures; both corrected, complete cohort rerun green. `py_compile` and `git diff --check` PASS.
- **P6 battery-selection source/fake subgate ACCEPTED**; P6/P7 overall still OPEN, AD148T final-owner pending, P8 full release/HW HOLD. No node104, real HA/ESP/Output, setpoint, charge, lease, firmware, deployment or remote Git.


## 2026-11-19 — recipe preview keyboard presentation owner (P6 batch 14)

The existing `runtime/ui/telegram/recipe_buttons.py` owns the read-only recipe
preview keyboard composition used by production START previews, including the
base preview rows, selectable active recipe versions, saved native recipe
versions and empty-catalog create entry. `production_bot_ui` retains direct
compatibility imports for `_preview_keyboard` and `_recipe_preview_keyboard`;
its registered handlers retain callback acknowledgement, pending START state,
recipe selection callbacks and transaction submission. Keyboard composition
does not authorize or execute charging. See
`.recipe-studio-local/REPORT_RD6018_P6_RECIPE_PREVIEW_BATCH14_20261119.md`.


## 2026-11-19 — independent P6 Recipe Preview owner batch-14 acceptance

- HOME-PC R7.2 Luna `rd6018-mod-p6-recipe-preview-owner-luna-20261119-14` exit 0; event `80f6048a41ff4624aaa27808d5a954fb` acknowledged on exact chat route attempt=1.
- Both existing `_preview_keyboard` and `_recipe_preview_keyboard` moved from `production_bot_ui.py` to existing `runtime/ui/telegram/recipe_buttons.py`; direct compatibility aliases retained. Active/archived recipes, native drafts, UTF-8 callback 64-byte cap, 24 selectable entries, missing/empty catalog and original START-first/recipes-next/navigation-last ordering preserved.
- Native Windows project venv thirteen-module full focused cohort **115 PASS + 66 subtests PASS**, exit=0. Independent host discovered two test expectations that did not match historical keyboard order/runtime monkeypatch; test assertions corrected, no production keyboard behavior changed. `py_compile` and `git diff --check` PASS. Earlier Linux system Python lacked aiogram/dotenv; those are not production regressions.
- P6 Recipe Preview source/fake subgate ACCEPTED; broader P6/P7 remain OPEN, P8 full regression/physical HOLD, AD148T final-owner unchanged. No node104, live HA/ESP, Output, battery, lease, firmware, deployment or remote Git push.


## 2026-11-19 — independent P6 PendingStart wizard owner batch-15 acceptance

- HOME-PC Codex Luna batch `rd6018-mod-p6-pending-program-state-luna-20261119-15` completed with exit=0 and emitted R7.2 completion event `4ce2469dee7945a093ff5e5a4319553a`; specific event ACK not separately verified. No parallel RD6018 Codex was launched.
- Existing Telegram charge owner now defines frozen `PendingStart`, `_pending_profile`, `_pending_intent`, `_pending_start`, `selected_program_for_user`, `_clear_pending_program_state`. `production_bot_ui` holds direct aliases, preserving DTO and dict identities, routing, and user-scoped state. `production_bootstrap._battery_start_route` clears only current user's wizard entries following accepted START and successful Telegram result delivery, retains them on rejection, exception or failed feedback. No charge/physical authority changed.
- Independent native Windows `.venv`: exact report 11-module cohort **111 PASS**, two unrelated deprecated UTC warnings, exit=0; extended registered UI callback/test cohort **92 PASS + 71 subtests PASS**, exit=0. During testing, corrected fixture's synthetic result to supply `port_result` and aligned AH-input-consumed `_pending_intent`/`awaiting_ah` assertions to actual pre-START lifecycle; pre-existing callback behavior was not altered. `py_compile` and `git diff --check` PASS.
- **P6 pending-wizard owner source/fake subgate ACCEPTED**. P6/P7 overall remain OPEN, AD148T final owner pending, P8 full release/physical acceptance HOLD. No node104, live HA/ESP, charging Output, V/I setpoint, lease, firmware, deployment or remote push.


## 2026-11-19 — graph workspace retirement seam (P6/P7 batch 16)

The existing `TerminalPanelManager` now performs the two graph workspace
retirement operations previously implemented inside the
`operator_dashboard.install_operator_graph_dashboard` closure. It already owns
the tracked graph/panel IDs and Telegram lifecycle. The dashboard renderer
delegates when that manager is installed and retains its pre-install fallback.
Registered graph/range callbacks, ACK/auth ordering, workspace render/edit
behavior, HANDS_OFF visibility, single bottom-panel behavior, and the existing
60-second refresh owner remain unchanged. Failure injection covers stale
Telegram deletion and replacement bookkeeping through the real manager.

This is function-level evidence only; `operator_dashboard.py` remains
MIXED-SCOPE and AD148 final-owner remains HOLD. Report:
`.recipe-studio-local/REPORT_RD6018_P6_OPERATOR_GRAPH_BATCH16_20261119.md`.
Linux assertions are blocked on missing `aiogram`/`aiosqlite` dependencies;
native Windows cohort pending. P6/P7 remain OPEN and P8 release/physical
acceptance remains HOLD.


## 2026-11-19 — independent P6 graph workspace lifecycle batch-16 acceptance

- HOME-PC Codex Luna run `rd6018-mod-p6-operator-graph-lifecycle-luna-20261119-16` completed exit=0; R7.2 event `0d23c8e484314f6ba584553345b546d6` ACK confirmed for exact route attempt=1.
- Existing `TerminalPanelManager` now owns best-effort removal of callback's old graph workspace and graph workspace for selected user; `operator_dashboard` delegates to this existing owner and preserves the pre-install compatibility fallback. Existing `forget_graph` owns ID retirement; no second graph/panel ID authority. Real registered operator_hmi graph handler and fallback/delete-failure/replacement behavior added to regression.
- Independent native Windows project `.venv` 13-module graph UI/dispatch/HANDS_OFF/entrypoint cohort **133 PASS + 71 subtests PASS**, three unrelated UTC deprecation warnings, exit=0. `py_compile`/`git diff --check` PASS. Executor's Linux system test collection lacked `aiogram`, `aiosqlite`, and audit test paths; those Linux errors are not treated as pass. Source/fake graph lifecycle subgate ACCEPTED. P6/P7 whole-project decomposition OPEN; AD148 final owner and P8 physical/full release HOLD.
- NOTE: Five P0–P9 plan/status blocks were previously out of sync due to historical pasted evidence inside the checklist; the executor synchronized the canonical repeated blocks while leaving the original checkbox states and approved statuses unchanged. This change is a document-sync repair, not approval of additional functionality. No node104, HA/ESP live, Output, charge, lease, firmware, deployment, remote push.


## 2026-11-19 — graph Telegram edit delivery seam (P6/P7 batch 17)

`runtime/ui/telegram/panel_lifecycle.py::deliver_graph_edit` handles graph caption/media Telegram edits and their existing best-effort exception semantics. It validates the supplied message ID against the existing tracked graph ID before delivery. It owns no cache or lifecycle state. `operator_dashboard.py` remains authoritative for samples, recorder-derived cache keys, rendering, live caption/keyboard selection and graph visibility policy; `TerminalPanelManager` remains authoritative for IDs, serialization, retirement and the single refresh schedule. Host behavioral acceptance is pending because local Linux test collection lacks `aiogram`; details and native Windows cohort: `.recipe-studio-local/REPORT_RD6018_P6_GRAPH_REFRESH_BATCH17_20261119.md`.


## 2026-11-19 — independent P6 graph refresh delivery batch-17 acceptance

## 2026-11-19 — graph initial publication owner seam (P6/P7 batch 18)

Bounded before/after production call graph:

```text
Before:
build_and_send_graph_dashboard
  -> publish_graph_workspace: query/chart -> Telegram send -> adopt ID -> cache -> start refresh

After:
build_and_send_graph_dashboard
  -> publish_graph_workspace: query/chart -> TerminalPanelManager.publish_graph_workspace
       -> send callback -> adopt_graph -> dashboard cache callback -> existing start_graph_refresh
```

`TerminalPanelManager` owns ordered publication and callback replacement lifecycle. Initial publication runs in the existing caller-held `ensure_last`/`publish_last` serialization context; callback edit→retire→replacement runs inside the existing `render_graph` lock. The dashboard remains owner of source samples, chart rendering, cache-key meaning/value, caption/markup and display policy, supplying those as callbacks. A Telegram send error propagates before new ID adoption, cache mutation or refresh startup. It rejects a callback whose message ID is no longer current before mutating range or rendering. Existing callback ACK/order, message order, HANDS_OFF/inactive guard, and one 60-second refresh task remain in force. Tests and limitations are in `.recipe-studio-local/REPORT_RD6018_P6_GRAPH_PUBLICATION_BATCH18_20261119.md`; P6/P7 remain OPEN pending native Windows and independent acceptance.

- HOME-PC Codex Luna `rd6018-mod-p6-graph-refresh-owner-luna-20261119-17` exited 0; R7.2 exact event `729c4478b70a4f6fb6b49d0006cb3a43` confirmed ACK attempt 1 in this chat.
- Existing `runtime/ui/telegram/panel_lifecycle.py::deliver_graph_edit` now owns stateless caption/media edit delivery, stale message ID fence and known Telegram error handling; `operator_dashboard` retains graph rendering, sample/query, cache key, policy and call registration. Existing TerminalPanelManager owns lifecycle and refresh task, no duplicate mutable authority.
- Independent native Windows project venv 13-module graph/dispatch/HANDS_OFF/composition cohort **138 PASS, 71 subtests PASS**, three unrelated UTC deprecation warnings, exit=0. Python compile and diff whitespace check PASS. Source/fake P6 graph delivery subgate ACCEPTED; P6/P7 overall OPEN, P8 physical/full release HOLD and AD148 whole-file owner HOLD. No node104, HA/ESP live, Output, charge, lease, firmware, deployment or remote push.


## 2026-11-19 — independent P6 graph publication batch-18 acceptance

- HOME-PC Codex Luna `rd6018-mod-p6-graph-publication-single-owner-luna-20261119-18` exit=0; completion event `aae4beb2784b48db92726cb67b815f5f` emitted via R7.2. Exact event ACK not separately asserted.
- Existing `TerminalPanelManager` now owns graph send/adopt/refresh initiation, stale callback fencing and edit -> retire -> replace ordering; dashboard retains graph source, rendering and cache contents. Range change occurs inside existing serialized callback path. Independent review discovered real *nested non-reentrant asyncio chat-lock deadlock* when `ensure_last()` -> dashboard -> `publish_graph_workspace()` acquired the same lock again; explicit Windows RED (`TimeoutError`) then GREEN after removing redundant inner lock, preserving caller's existing lock. Regression `test_ensure_last_graph_publication_uses_existing_chat_lock_without_deadlock` remains.
- Independent native Windows `.venv` graph/dispatch/HANDS_OFF/UI suite **145 PASS + 71 subtests PASS**, three UTC deprecation warnings, exit=0. Cross-area START/recipe/graph/terminal suite **163 PASS + 71 subtests PASS**, two UTC deprecation warnings, exit=0. `py_compile` and `git diff --check` PASS. Linux system tests blocked on missing `aiogram`, not counted as PASS.
- P6 graph publication source/fake subgate ACCEPTED; P6/P7 overall OPEN, P8 physical/full release HOLD, AD148 whole-file owner HOLD. No node104, HA/ESP live, physical Output, V/I setpoints, lease, charge, firmware, deployment or remote push.


## 2026-11-19 — P7 ownership recovery HMI projection, batch 35

Removed `rd_ownership_recovery.install_rd_ownership_recovery`'s process-global assignment to `operator_hmi.build_operator_keyboard`. The existing `runtime/ui/components/hmi_action_keyboard.py` now projects ownership controls from the current app's `rd_control_mode_manager`, managed-session flags, D061 adoption coordinator and HMI state; `operator_hmi.build_operator_keyboard` invokes it before the existing final Output-truth/Autonomous filters. Existing callback labels remain in `runtime/ui/labels/operator_actions.py`; row construction uses `runtime/ui/telegram/renderer.py`. Callback registration, idempotent per-app install marker, recovery/release/adoption handlers and ExecutionPort routing are unchanged. `operator_managed_stop.py` remains untouched. Dependency-free `tests.test_p7_ownership_hmi_contract`: **3 PASS**; Python compilation and `git diff --check` pass. Linux `tests.test_rd_ownership_recovery` collection is blocked by missing `aiogram`. Windows project `.venv` cohort is pending; no Windows PASS is claimed. Owner: existing UI component; bounded source implementation for R7.2 run `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35`, which the controlling ChatGPT had already launched. This local review did not invoke/inspect the route and does not claim completion or ACK. Code HEAD remains `50ea5f92`, branch `feature/main-mix-countdown-display`, 45 commits ahead of tracking origin; no remote query, commit or push. WIP remains uncommitted for independent host acceptance. Next executable step: run the exact Windows project `.venv` cohort in the batch report and inspect actual markup, composition order, stale callback handling and Output/Autonomous filters. Linux runtime unittest is blocked before assertions by missing `aiogram`; this and Windows acceptance are HOLD. Starting node104 HANDS_OFF/deployment state was not refreshed and is not asserted as current. P7 remains PARTIAL; P8 full Linux/Windows/physical release HOLD; AD083/AD148 whole-file HOLD; no checklist promotions. No node104, live HA/ESP, Output/V/I, charge, lease, firmware, service, deployment, remote push, BW600 or XH-CDC-MK action. Report: `.recipe-studio-local/REPORT_RD6018_P7_OWNERSHIP_HMI_BATCH35_20261119.md`.


## 2026-11-19 — independent P7 ownership-recovery keyboard batch-35 acceptance

- HOME-PC Codex Luna `rd6018-mod-p7-ownership-hmi-owner-luna-20261119-35` exit=0, R7.2 completion event from shared launcher. Removed `rd_ownership_recovery.py`'s process-global `operator_hmi.build_operator_keyboard` assignment and first-app closure. Existing `runtime/ui/components/hmi_action_keyboard.py::_ownership_recovery_keyboard` now uses each app's installed recovery marker, control-mode manager, D061 owner and active managed state. No new app field/authority/manager. Existing Telegram callback registration and physical ExecutionPort transactions are retained. Original operator managed-stop wrapper is still separate and unchanged.
- Independent Windows project `.venv`: focused ownership/stop/D061/Output-truth/autonomous/production cohort **110 PASS + 31 subtests PASS** after fixing one real cross-app pre-install button leak and one fake callback registry missing its routes list. Expanded 21-module ownership/D062/graph/START/production/lifecycle/physical wiring suite **235 PASS + 102 subtests PASS**, two preexisting UTC deprecation warnings, exit 0. New fake/AST test checks installed per-app owner and source-only no global builder assignment. `py_compile` and `git diff --check` PASS.
- Scoped P7 ownership recovery HMI projection ACCEPTED. Original P0–P9 status/checklist remains unchanged: P7 PARTIAL, P8 full Linux/Windows/physical/release HOLD, AD083/AD148 whole-file HOLD. No live node104/HA/ESP, Output, V/I, charging, lease, firmware, service, deployment or remote push.

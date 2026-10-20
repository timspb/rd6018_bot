# D123 Sprint 40 — application-owned controller action execution

Baseline: Sprint 39 commit `68ffd4e7caffb8f07b50a932c3e50083c6df4f02`. Isolated WSL2 source worktree only. No HA, ESPHome, production service, credential, firmware, or hardware access/change.

## Change

Moved controller action-batch transaction orchestration from `runtime.production_runtime` into `application.controller_action_execution.execute_controller_action_batch`. The runtime function remains a dependency-binding adapter. The use case delegates physical sequencing and verification to the existing `ExecutionPort`, then performs the existing verified-enable stage commit only after successful physical verification. If Output was enabled but the transition cannot be committed, it requests verified OFF. Existing logging, event and notification effects are retained.

No stage/recipe decision, safety gate, setter, second execution owner, journal, or persistence path was added. The runtime-wide guard-owner lock remains at the caller surrounding decision, batch execution, and state checkpoint.

## Verification

- Focused application batch, recovery resume, final SAFE_WAIT, execution convergence, Guard and migration set: **52 PASS**.
- Full offline Python 3.12 discovery: **2,435 PASS / 3 skipped**.
- `python -m compileall -q .`: PASS.
- `git diff --check`: PASS.
- Live/physical acceptance: not run; no production mutation.

This closes only the action-batch application ownership cut. P3 remains incomplete: controller `tick` still owns session orchestration and mutable action assembly; stage commit remains a controller callback; Manual integration and broader session/DONE ownership remain open. P4 facade retirement is not part of this change.

Synthetic test token only: `TG_TOKEN=123456789:d123-sprint40`.

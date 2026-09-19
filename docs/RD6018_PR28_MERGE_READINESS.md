# RD6018 PR #28 Merge Readiness

Status: `BLOCKED_WITH_REASONS`

Audit scope: PR #28, `ef2b4806a16723eaff67451667d0a2c73fca8fc4..61be65388a273dd12223322bbe0e3df8468e11d2`.

## 1. Changed-file scope

PR #28 contains 630 changed files: 578 added and 52 modified.

This is not limited to ExecutionPort consolidation and the Python 3.11 fix.
It also contains:

- 81 `application` files;
- 170 `runtime` files;
- 156 documentation files;
- 163 test files;
- physical, safety, lease and runtime configuration;
- broad changes to `bot.py`, `manual_mode.py`, `runtime/v2_runtime.py` and
  `bot_legacy.py`.

Therefore the requested scope classification is:

- `A — required migration`: ExecutionPort, manual boundary migration, related
  identity/audit tests and the two dataclass compatibility fixes;
- `B — supporting`: directly related focused tests and migration documentation;
- `C — unrelated or insufficiently bounded for this PR`: the remaining
  accumulated V3/runtime/physical/configuration/docs/test layers.

## 2. Execution ownership

### PASS — intended V2 owner

The canonical WS124 path is:

`Manual intent -> ExecutionIntent -> ExecutionPort -> existing V2 owner -> HA/RD`

`application/execution_port.py` does not select phases or targets. It delegates
to the existing V2 owner and verifies readback.

### PASS — manual direct bypass check

The current `manual_mode.py` path no longer calls the hardware setter directly;
manual start, stop, cooling, resume and error shutdown go through
`ExecutionPort`.

### BLOCKER — secondary write-capable surfaces remain in the PR

The PR still adds or carries write-capable surfaces including:

- `runtime/output/bridge/executor.py` (`PhysicalBridgeExecutor`);
- `runtime/physical/connectors/esp_direct.py`;
- `runtime/physical/connectors/ha_esp.py`;
- `runtime/physical/transports/ha102.py`;
- `runtime/physical/commands/**`;
- `physical_test_control_pb_mode.py`;
- `tools/physical_test_autonomous_client.py`.

These are not removed or independently proven quarantined by this PR. Their
presence prevents confirmation of the strict single-execution-owner invariant.

## 3. Safety and lease boundaries

Not confirmed unchanged. The PR changes safety/ownership surfaces, including:

- `edge_safety_lease.py`;
- `runtime/physical/lease/**`;
- `runtime/safety/**`;
- `application/ownership_transition.py`;
- physical and safety configuration;
- managed-adoption and ownership-recovery modules.

The 900-second lease/local-autonomous semantics require a separate focused
review against the current source-of-truth documents before merge.

## 4. Validation evidence

- GitHub Actions: Python 3.10 PASS;
- GitHub Actions: Python 3.11 PASS;
- GitHub Actions: Python 3.12 PASS;
- CI unit tests: 1714 tests per matrix job;
- CI compile step: PASS;
- PR diff-check: FAIL — trailing whitespace and blank lines at EOF in many
  files, including `runtime/v2_runtime.py` and accumulated documentation;
- local compileall: PASS on the current workspace.

The CI workflow does not currently enforce the failing PR diff-check result.

## 5. Node101 safety

No node101 deployment, service restart, configuration mutation or hardware
action was performed during this audit. PR metadata contains no deployment
operation.

## Decision

`BLOCKED_WITH_REASONS`

PR #28 is not ready to merge as a bounded execution-plane consolidation.
Before merge, either split the accumulated migration into separately reviewed
PRs or explicitly review and accept every added runtime/physical/safety/lease
surface. The physical execution-owner consolidation and PR diff hygiene must
also be revalidated after that boundary is established.

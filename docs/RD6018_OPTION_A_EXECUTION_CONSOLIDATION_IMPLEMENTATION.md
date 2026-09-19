# RD6018 Option A — Execution Ownership Consolidation

Status: `BLOCKED_WITH_REASON`

## Boundary

The release tree keeps one physical ownership path:

`V3 ExecutionIntent → ExecutionPort → V2 physical owner → existing adapters → RD6018`

`ExecutionPort` remains the only V3-to-V2 execution boundary. It delegates
approved, safety-checked intents to the injected V2 owner and verifies the
result. No lifecycle or target decisions were moved into an adapter.

## PhysicalBridgeExecutor

`runtime/output/bridge/PhysicalBridgeExecutor` is now a fail-closed,
import-compatible compatibility surface. Its former write operations reject
immediately and cannot call a transport. Readback verification and contract
types remain available for diagnostics and migration compatibility.

## Physical adapters and connectors

The ESPHome and Home Assistant connector/transport surfaces retain discovery,
health, snapshots, readback, and capability reporting. Their write methods are
read-only rejects; they do not issue service calls, Modbus-style writes, or
ESPHome commands. V2 remains the physical owner and existing V2 safety and
lease semantics are unchanged.

## Manual paths

Manual start, stop, error-shutdown, cooling-shutdown, and MAIN→MIX target
updates continue through the existing intent and `ExecutionPort` boundary.
`manual_mode.py` has no direct actuator calls.

## Validation

- ownership invariant tests: added in `tests/test_workstream133_execution_owner.py`;
- focused legacy bridge tests: updated to assert fail-closed behavior;
- safety and lease logic: unchanged;
- no deployment, service restart, or hardware action performed.

Focused WS133/WS124/WS113B, safety, lease, compileall, and working-tree
`git diff --check` passed. The release gate remains blocked because the full
suite cannot complete in the current Windows environment (`OpenBLAS error:
Memory allocation still failed after 10 retries`) and the complete migration
range already contains 185 EOF-whitespace findings in `git diff --check
main...HEAD`. These are release hygiene/environment blockers, not ownership or
hardware findings.

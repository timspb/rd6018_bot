# P1-AD087 — HANDS_OFF verified OFF and D061 false-result implementation decision
Date: 2026-11-15
Status: IMPLEMENTATION APPROVED — narrow existing-owner change; source/fake only.

## Accepted implementation contract

AD084 correctly identified the two defects and the bool/cancellation semantics. Its preference for routing the HANDS_OFF operator action through normal serialized request_verified_off is NOT adopted. Independent reconciliation against AD027/AD029 and the current production wrappers shows that would change existing behavior: RdControlModeManager.operator_output_off currently calls the same guard's _ensure_output_off directly, which uses the existing guard _off_lock but bypasses the app GuardExecutionOwnerLock and startup gate. Explicit operator OFF must retain that liveness and startup behavior.

The smallest behavior-preserving route is the existing ExecutionPort.request_emergency_off, not a new port or lock:
- Add a default-deny, narrowly scoped optional argument to the existing request_emergency_off API, e.g. allow_hands_off_operator_off=False.
- Only that existing method may pass the explicit OFF exception to _normal_actuation_gate. The exception applies only to action "Output OFF" while the manager is HANDS_OFF. It must NOT bypass edge_autonomous: the existing rd_autonomous_mode wrapper rejects the capability while AUTONOMOUS (rd_autonomous_mode.py:216-230), and the ExecutionPort gate must independently keep rejecting autonomous.
- Keep request_emergency_off's existing app-lock bypass and ignore_startup=True semantics. This matches the existing direct manager path. The same ManagedRuntimeSafetyGuard remains _execution_owner and its existing _off_lock, post-command verification and OFF-unconfirmed latch remain mandatory. No raw adapter access from manager.
- Preserve optional entity_id supplied by operator UI by extending the existing method's optional argument and forwarding it to the same owner's turn_off; omit the argument when None for compatibility with existing fakes.
- No PB_MANAGED mode transition. Existing manager HANDS_OFF precondition and residual lease-disarm-after-positive-OFF ordering remain.
- Existing simple OFF methods do not emit structured ExecutionPortAudit records. Do not invent a second audit store or claim this change adds an audit record; document this existing limitation.

This is an explicit operator OFF override, not permission for normal HANDS_OFF bot actuation. Ordinary request_verified_off, ON, V/I, restore, start and all other callers remain default-deny. No autonomous OFF override.

## D061 false-result correction

In rd_managed_adoption.py _verified_off:
- Preserve the initial OFF_PENDING state/status persistence before the actuator await.
- Capture the returned bool from the selected existing call: HANDS_OFF manager.operator_output_off; PB_MANAGED request_emergency_off; verified_stop request_verified_off.
- If false, persist an unconfirmed status and return false immediately. Keep OFF_PENDING, Manual session state/request/task, and lease state intact. Do not disarm, retire Manual, set FAILED, or claim "Output verified OFF".
- Only a positive true result may proceed to existing best-effort lease disarm, Manual retirement, FAILED state and verified status.
- Ordinary Exception remains an unconfirmed false result. asyncio.CancelledError continues to propagate (do not catch BaseException); OFF_PENDING is already persisted, so cancellation must not retire Manual or claim OFF.
- No typed Native receipt conversion: this change enforces the existing bool contract only. Keep generic Safety verified-OFF bool distinct from ExecutionPort.request_verified_off_evidence and AD051 firmware APPLIED/R18 receipt.

## Source and test allowlist

Production source:
1. application/execution_port.py
2. rd_control_mode.py
3. rd_managed_adoption.py

Tests:
1. tests/test_execution_port_policy_boundary.py
2. tests/test_rd_control_mode.py
3. tests/test_rd_managed_adoption.py

Do not edit runtime/safety/runtime_guard.py, rd_autonomous_mode.py, ESPHome/connector/transport/firmware, AD051, START transaction, persistence, any other source/test, registry/CSV or generated artifacts. Preserve all pre-existing WIP/hunks in allowlisted files; make the smallest contextual edits only.

## Required regression behavior

- Default request_emergency_off in HANDS_OFF remains denied.
- Explicit allow_hands_off_operator_off=True permits only Output OFF while HANDS_OFF and not edge AUTONOMOUS; ON/V/I and normal verified OFF remain denied.
- Edge AUTONOMOUS still blocks the explicit capability (both wrapper and port gate).
- Manager uses the existing app ExecutionPort, preserves entity_id, stays HANDS_OFF, and only disarms residual lease after true.
- Existing app lock bypass for emergency OFF remains; guard _off_lock and Safety verification remain. Do not serialize this route with the normal app lock.
- D061 tests cover true, false, exception and cancellation for HANDS_OFF manager, PB emergency and PB verified_stop branches as applicable. False/exception/cancel leave OFF_PENDING and Manual state/lease intact; true preserves existing retirement order.
- Existing ExecutionPort lock, verified-OFF, autonomous-mode, adoption and Manual regression cohorts pass.

## Explicit exclusions

No new guard, port, adapter, lock, queue, worker, timer, poller, state store, token or cryptographic authorization. No broad HANDS_OFF gate relaxation; no edge-autonomous exception; no ON/V/I permission; no change to startup/quarantine policy outside the existing request_emergency_off ignore_startup behavior; no AD072 START cancellation repair; no firmware/HA/ESP Native/node104/physical/deployment action.

## Evidence and acceptance

Sources: AD084 report, AD085 report, AD027/AD029 prior decisions, current execution_port.py, rd_control_mode.py, rd_autonomous_mode.py, rd_managed_adoption.py and tests. The AD079 full report was independently reviewed from its actual path .recipe-studio-local/REPORT_MOD_P1_AD079_CONTROL_ADOPTION_OWNER_AUDIT_20261115_FULL.md; AD084's task mistakenly listed docs/RD6018_AD079... as the path, which does not exist.

Codex implementation is authorized only within the allowlist above. Independent Windows project .venv tests and git diff --check are required before accepting. No stage/commit/push/reset/clean/stash/checkout. START/release remains HOLD until the separate AD072/AD040/AD041 atomic persistence and cancellation-settlement contract is closed.

# B1026 — typed ON receipt observation review

Run: `rd6018-b1026-20261126-r73-typed-on-receipt`
Branch: `codex/rd6018-b1026-typed-on-receipt-20261126`
Baseline/source HEAD: `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa`
Disposition: **PRODUCTION PATCH NOT SAFE TO PROVE IN THIS BOUNDED CUT; EXACT LIMITATION AND SOURCE-ONLY FIXTURE PLAN RECORDED**

## Scope and result

Reviewed the requested P0–P9 canon and the focused B1020, B1024 and B1025 records. Audited the production call graph from `ExecutionPort.request_verified_on()` through the safety owner, `HassClient`, `ESPDirectConnector`, and `ESPHomeTransport.command_output_with_receipt()`, including strict/managed guard overrides, Native report access, recovery barriers, HANDS_OFF barriers, and the existing OFF receipt path.

The gap is confirmed: ESP Native produces the real immutable `OutputCommandReceipt`, but its typed value is discarded before it reaches the application. No non-invasive existing read can recover that exact ON receipt afterwards. A cache or “last receipt” accessor would permit stale or cross-request reuse. Adding a second receipt-aware actuator call in only one layer would risk diverging from the existing safety transaction.

I made no production, test, firmware, configuration, or shared canonical-document changes. The requested implementation subgate is therefore **NOT CLOSED**. P3 live/physical and B1020 Gate 3 remain **HOLD**; no physical ON/OFF evidence was collected. P0–P9 remains **98/103**, with three P3 and two P8 physical/release gates on HOLD.

## Exact production path and loss point

1. `application/execution_port.py:516-523` — `request_verified_on() -> bool` applies recovery quarantine, guarded-restore latch, output authority, then returns `bool(await self._execution_owner.turn_on())`.
2. Production execution owner is the composed safety owner. `runtime/safety/runtime_guard.py:516-550` handles prior-OFF containment, calls captured `_raw_turn_on`, validates fresh live telemetry and envelope after ON, and invokes verified OFF containment on false/exception/invalid post-ON evidence.
3. `runtime/safety/strict_guard.py:205-238` overrides `turn_on()` to require an active session, positively arm the existing edge lease before parent ON, then disarm after verified OFF cleanup.
4. `runtime/safety/managed_guard.py:382+` overrides `turn_on()` with managed OFF-recovery and external-temperature latch/re-authorization behavior before delegating to the strict owner.
5. `hass_api.py:358-360` routes `turn_on()` to `_switch_service()`. For the physical backend, `_switch_service()` calls `enable_output()` and normalizes success to `True`.
6. `runtime/physical/connectors/esp_direct.py:69-70` calls `transport.command_output(True)`. `runtime/physical/transports/esp128.py:553-555` unwraps the actual typed receipt into decoded JSON. `:557-607` constructs the real `OutputCommandReceipt` only for terminal `APPLIED` with matching target and R18; `:621-622` clears its request-correlated in-flight state.
7. `ExecutionPort.read_native_physical_output_report()` and the Safety owner’s `get_native_physical_output_report()` are read-only Native report paths. They return no completed command receipt and cannot reconstruct request ID, terminal identity, or command completion time.

The receipt can only be preserved at the existing command invocation, then carried through every post-command safety check without a second command, stale slot, or bypass. A correct implementation therefore needs the receipt to travel through the same common transaction used by all three safety-guard levels; it cannot be safely added as a connector-only optional API.

## Minimal source-only implementation and fixture plan

Implement only after the common safety transaction can be refactored without changing its ordering or containment:

- Keep the existing public `request_verified_on() -> bool` contract and all callers unchanged.
- Add the bounded observation entrypoint `ExecutionPort.request_verified_on_with_receipt() -> tuple[bool, OutputCommandReceipt | None]`. Both public methods must enter one private, app-lock-serialized ON transaction and execute the same authorization gates, lease operations, raw ON invocation, post-ON telemetry/envelope checks, and failure containment. The existing method projects only the boolean. The observation method may return only the typed receipt produced by that invocation and only alongside the final transaction result; no receipt cache, persistence, background observer, inferred receipt, or alternate owner.
- Carry the optional receipt from `HassClient.turn_on()`’s existing physical-backend call through the same connector and safety-owner transaction. `HA102` and any backend lacking a typed receipt return `None`; they do not synthesize one. The regular boolean behavior stays unchanged.
- Preserve guards: guarded restore latch and recovery quarantine block before transport; HANDS_OFF/autonomous/release barriers remain default deny; guarded restore only clears from its existing positive guarded-resume receipt; strict lease arm must positively acknowledge before the one ON; post-ON validation failure still executes the current verified-OFF containment; transport exception retains current cleanup.
- Add fake-only tests around the existing `ExecutionPort` and safety owner: (1) one physical ON invocation for a successful receipt path; (2) legacy bool remains exactly the same for true/false/exception outcomes; (3) returned receipt is the exact object from that call, and a later call without receipt support cannot return it; (4) post-ON safety failure retains OFF containment and does not expose success; (5) guarded restore latch and recovery quarantine make zero ON calls; (6) HANDS_OFF/autonomous/release barriers make zero ON calls; (7) strict lease-arm rejection makes zero ON calls; (8) no OVP/OCP admission/write behavior is added. Keep B1024’s typed receipt and causal Native validation fixtures as the consumer check.

This fixture plan is not implemented in this B1026 cut. First proof blocker is the subclass-specific safety transaction composition: a receipt-aware wrapper that merely calls existing `turn_on()` cannot obtain the receipt, while a parallel override that reimplements any portion can drift from the current authority path. The prerequisite is a reviewed common transaction seam across Runtime, Strict, and Managed guard methods, with before/after ordering preserved by source review and fake parity tests.

## Verification

Offline project venv command:

```text
PYTHONPATH=.:tests:tools TG_TOKEN=<inert-local-value> /home/home-pc/.venvs/pcp-test/bin/python -m unittest \
  tests.test_b1024_native_phase_evidence \
  tests.test_execution_port_policy_boundary \
  tests.test_managed_runtime_safety \
  tests.test_d123_sprint57_guard_native_evidence \
  tests.test_rd_hands_off_transfer_barrier -v
```

Result: **78 tests PASS**, exit 0. This is existing source/fake regression evidence only; it does not prove the proposed receipt propagation, live Native callbacks, or hardware behavior. No full CI, installation, network, node104/ESP/HA/RD hardware, service, lease, firmware, setpoint, or Output action was run.

`git diff --check`: PASS after report/doc creation. No staging, commit, or push. Existing Wake R7.3 callback/ACK was not manually invoked and no separate R7.3 ACK is claimed.

## Exact changed paths and boundaries

- `B1026_REPORT.md`
- `docs/acceptance/B1026_ON_RECEIPT_OBSERVATION.md`

No source or tests changed. Shared checkpoint, master plan, handoff canon and project runbook were intentionally not edited; controller reconciliation remains outstanding. Node104 HANDS_OFF/deployment state and local/origin gap were not freshly queried. No production source acceptance, release acceptance, physical acceptance, or checklist promotion is claimed.

Next executable step: have the architecture owner decide whether to extract one shared Runtime/Strict/Managed ON transaction seam first. If accepted, implement the seam and receipt propagation together with the exact fake cases above; then independently review B1024 evidence assembly. B1020 Gate 3 remains HOLD until separately supervised physical acceptance.

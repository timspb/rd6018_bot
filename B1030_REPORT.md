# B1030 — ON receipt path audit

Run: `rd6018-b1030-20261126-r73-shared-on-transaction`
Branch: `codex/rd6018-b1030-shared-on-transaction-20261126`
Base/current Git HEAD: `56a42c097d0bd753f124a8a98be56246ded1f50d`
Worktree was clean at start. No production source, runbook, checkpoint, master
plan, or handoff canon was changed. No stage, commit, push, network, service,
device, or physical action occurred.

## Composition and execution path

`bot.py`'s `ProductionComposition.compose()` calls
`production_bootstrap.install_production()` on the `runtime.production_runtime`
substrate; this is composition, not a second physical owner. The runtime's
deferred `hass` is bound at startup by `initialize_runtime()` to
`HassClient.from_physical_config()`, which selects `default_connector` from
`config/physical/connectors.yaml`. This exact worktree selects **`esp_direct`**,
not HA102. `production_bootstrap.install_production()` installs
`ManagedRuntimeSafetyGuard` as the explicit Safety owner (`patch_adapter=False`)
and obtains the app-scoped `ExecutionPort`.

The configured guard MRO is:

```text
ManagedRuntimeSafetyGuard.turn_on
  -> StrictRuntimeSafetyGuard.turn_on
      -> RuntimeSafetyGuard.turn_on
          -> captured HassClient.turn_on
```

`ExecutionPort.request_verified_on()` is the serialized bool API. It checks
recovery/guarded-restore containment and ownership authority, then calls
`bool(await execution_owner.turn_on())` once. Production callers include
controller actions, MAIN Guard, operator pause resume, and session recovery.
The app-scoped owner lock remains the serializer.

Within the guard chain, the base guard reconciles any prior OFF containment,
executes one raw ON, then checks fresh live Output, critical telemetry, and the
runtime envelope. `StrictRuntimeSafetyGuard` requires acknowledged edge-lease
arm before calling its parent, and handles OFF containment and lease disarm on
failure. `ManagedRuntimeSafetyGuard` applies external-temperature integrity
and reauthorization rules, and may clear its durable fault latch only after
successful parent checks. These distinct overrides must remain in the call.

## Receipt loss

The typed `OutputCommandReceipt` exists at the ESP transport terminal
`APPLIED` event, but the production ON path erases it before the guard:

1. `ESPHomeTransport.command_output_with_receipt(True)` creates the immutable
   typed object. Existing `command_output(True)` decodes its terminal JSON
   identity and returns a dict.
2. `ESPDirectConnector.enable_output()` awaits that command and returns
   `None`, dropping even the decoded dict.
3. `HassClient._switch_service("turn_on")` awaits backend `enable_output()`
   and returns `True`; it intentionally discards any backend result. HA102's
   REST `enable_output()` also returns no typed Native receipt.
4. `RuntimeSafetyGuard.turn_on()` converts the raw adapter result to bool;
   Strict and Managed guards preserve bool outcomes after their own checks.
5. `ExecutionPort.request_verified_on()` converts the final owner result to
   bool again.

Therefore there is no exact receipt object left to present at the application
boundary. The current checked-in default is direct ESP Native, so it is not
correct to assume this checkout defaults to HA102. If HA102 is selected, a
Native typed receipt remains unavailable and the eventual presented value must
be `None`.

There is another existing ON entry path: `ExecutionPort.enable()` runs the
same owner lock and the existing `SafeOutputCoordinator`; it performs V/I
programming and readback before calling `turn_on()`, then performs a distinct
final readback before returning success. A common receipt presentation point
must be after those final checks too. Presenting from the base guard would be
premature for both the Strict/Managed tail checks and the coordinator's final
verification.

## Decision and minimum next cut

No production change was made. A safe change needs a per-invocation receipt
capture carried through the existing ON call, plus a later presentation owned
by each existing transaction boundary. It must not add a second ON method,
cache the receipt on a long-lived object, or move any guard check. The minimum
refactoring cut is:

1. Extend the existing transport/connector/`HassClient.turn_on` path with an
   optional internal capture sink. On direct ESP, send the exact typed object
   from the existing command invocation to that sink while retaining legacy
   bool/return behavior. HA102 does not call the sink.
2. Carry one request-local capture slot through the existing
   `RuntimeSafetyGuard`, `StrictRuntimeSafetyGuard`, and
   `ManagedRuntimeSafetyGuard` override chain. Keep `request_verified_on()`'s
   bool result and call the optional presentation callback only after the
   final Managed guard has returned success. False, exception, failed
   readback, OFF containment, lease failure, HANDS_OFF denial, or guarded
   restore denial must present nothing (equivalent to `None`).
3. For `ExecutionPort.enable()`, carry the same per-call receipt through the
   existing `SafeOutputCoordinator` and present it only after its final
   post-ON readback accepts. Do not create a second execution or ON command.
4. Keep the callback optional; existing callers retain bool/result parity.
   Callback failure must not convert a physically successful transaction into
   a false result or invoke another Output command. Test exception behavior
   before introducing the change.

The cut spans connector, adapter, three guard overrides, ExecutionPort and
SafeOutputCoordinator. B1030 did not establish a sufficiently narrow
implementation with proofs for both ON entry paths, so the request's
no-bypass/no-duplicate conditions are not met by a partial patch.

## Offline fixtures and checks

Added three focused tests in
`tests/test_b1030_on_receipt_boundary.py` for the typed transport-to-connector
loss, the HassClient bool boundary, and ExecutionPort bool/single-call parity
plus the actual guard MRO. They use fakes only and make no physical claims.

Evidence:

- Project venv: `/home/home-pc/.venvs/pcp-test/bin/python`
- Focused command:
  `/home/home-pc/.venvs/pcp-test/bin/python -m unittest tests.test_b1030_on_receipt_boundary -v`
  — **3/3 PASS**, exit 0.
- `py_compile` over the new fixture and all seven traced production owners —
  **PASS**, exit 0.
- `git diff --check` — **PASS**, exit 0.
- No full suite or CI run.
- P0–P9 remains 98/103; P3 physical (3) and P8 release (2) remain HOLD.
- No node104, ESP/HA/RD hardware, firmware, Output, setpoints, SSH, network,
  deployment, service, or original dirty worktree was accessed.

## Exact changed paths

- `B1030_REPORT.md`
- `tests/test_b1030_on_receipt_boundary.py`

Production source changes: **none**. Worktree remains source-only and
uncommitted, based at the requested HEAD.

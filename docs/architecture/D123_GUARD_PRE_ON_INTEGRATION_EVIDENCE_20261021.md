# D123 Guard pre-ON integration evidence — 2026-10-21

Starting source: `804a2273406990ed6e0bea28798ab39397fd2fdd`, branch
`codex/d118-start-lease-repair-20261019`. Source-only work; no hardware,
HA, firmware, services, deployment, or network calls were made.

## Flow and result

Before this cut, `restore_session` rejected a Guard-bearing document before
controller mutation. Deferred startup restore then read `app.hass.get_all_live()`
and used that aggregate for ordinary unguarded restore and resume. The pure
`assess_main_guard_before_output_on` already validates direct Native metadata,
freshness, independent OFF, matching Iset/OCP, Guard journal identity/revision,
lease and owner authorization, but no production caller connected it to
deferred startup.

After this cut, persistence retains the Guard-bearing document in a frozen
`GuardedRestoreCandidate` with identity, journal revision when structurally
available, and an explicit `direct_native_pre_on_reconciliation_required`
blocker. This is quarantine only: FSM stage/profile, trace identity, active
Guard and session writer are untouched. Deferred startup detects this candidate
under its existing owner lock and returns before reading HA aggregate data or
attempting enable. Corrupt and mismatched journals remain blocked; no authority
is inferred from candidate fields.

Guard pre-ON is **not fully integrated**, and Guard-bearing sessions cannot
activate. This source cut stops at outcome B: fail-closed quarantine is explicit
and typed, while Native acquisition and activation remain unimplemented.

## Normal Output-ON routes and lock coverage

- Explicit START: `application.start_transaction_service` acquires the
  app-scoped `ExecutionPort._guard_owner_lock` around the full START transaction.
- Deferred startup resume: `runtime.startup_recovery` wrapper acquires that
  same lock. Guard candidates now return before HA read/restore/ON. Unguarded
  restore retains its existing flow.
- Runtime charge decisions and controller action execution: the production
  application tick in `runtime.production_runtime` runs decision/checkpoint/
  physical action in the app-scoped owner lock; nested normal `ExecutionPort`
  operations use its task-reentrant lock.
- MAIN Guard reductions use that same lock via `execute_due_main_guard` and
  the same app-scoped port; this path does not enable Output.
- Other named resume/action owners route verified ON through the same port or
  through production controller-action execution. No independent production
  ON route was added by this change.
- Emergency verified OFF remains independent: `ExecutionPort.request_verified_off`
  is intentionally not decorated with normal owner serialization.

## Native evidence and remaining boundary

The pre-ON contract requires fresh Native `SensorState` metadata and values for
`output_state_code_v2`, `set_current_readback_v2`, `ocp_readback_v2`, and
`protection_code`; output code must independently prove OFF, protection must
be normal, and programmed Iset/OCP must already match the target and persisted
monotone ceiling. Missing/stale evidence, unresolved Guard pending/fault,
identity/revision mismatch, unarmed lease, or missing owner authorization
must block. The assessor does not program Iset/OCP and has no hardware writer.
HA/cache metadata cannot satisfy this contract.

The current startup recovery API exposes only `app.hass.get_all_live()` on this
path. The repository's direct Native connector/transport is an existing
physical subsystem, but no already-owned startup/recovery method provides a
fresh callback snapshot with the required provenance to this caller. We did
not invent a new transport, make a live call, or treat aggregate data as Native.
The remaining source boundary is to expose an existing direct-Native snapshot
through its current owner and assess while the shared lock is held, then define
and test an atomic, revision-revalidated activation into the sole controller
session. Until that work is source-proven and later physically accepted,
GuardedRestoreCandidate remains quarantined and no guarded Output-ON is
possible.

## Ownership and verification

The canonical journal reader/revision authority remains
`runtime.charge.strategy.main_guard_session.read_guard`; persistence remains
the sole session writer; the existing `ManagedChargeController` host and
app-scoped `ExecutionPort`/`GuardExecutionOwnerLock` remain singular. The
candidate is a typed quarantine value, not another FSM or persistence owner.

Validation on Python 3.12: focused source-safe Guard/startup/owner tests passed
**61/61** (`test_startup_recovery`, `test_main_guard_pre_on`,
`test_main_guard_session`, `test_output_enable_inventory`,
`test_main_guard_transaction`, `test_d123_sprint30_session_seam_blocker`).
`compileall` and `git diff --check` passed. Guarded legacy restore and START
service suites could not import because the available interpreter lacks
`python-dotenv` and `aiogram`; dependencies were not installed. Full discovery
ran **1,326 tests**, with **2 failures, 197 errors, 3 skipped**; import errors
from missing dependencies include `aiogram`, `aiohttp`, and `python-dotenv`,
and unrelated dependency/CLI test failures also appear. This is not a passing
full suite and does not replace the previously verified 2,463-test baseline.

Outer verification with the existing full-dependency Python 3.12 venv:
36 focused Guard/startup/Native/owner tests PASS; compileall and diff-check PASS.
Full discovery without a synthetic Telegram bootstrap token ran 2,352 tests,
18 import errors due to the missing token, 3 skipped. This does not establish
full-suite regression failure; rerun with a synthetic token before release.

# D123 Sprint 57 — P2 read-only Native Guard evidence

## Scope and baseline

Source-only continuation from clean HEAD
`8646dc3b49ac70e6c1cc3f33ab94830fe79ca830` on
`codex/d118-start-lease-repair-20261019`. Work stayed in the writable WSL2
checkout. No node104, ESP, HA, production, services, firmware, deployment,
network, or physical Output access/actions occurred. No dependencies were
installed.

P4 remains closed. There is still exactly one canonical controller/FSM/session
owner and the existing app-scoped `ExecutionPort`/`GuardExecutionOwnerLock`.
No recipes, lease behavior, safety, OVP/OCP, Manual policy, or priority changed.
Guard restore activation remains deferred and fail-closed.

## Native snapshot and owner path

`HassClient.get_native_guard_pre_on_snapshot` is the one read-only API for the
Guard evidence cut. It requires an actual existing `ESPDirectConnector` backend;
HA-only selection returns no snapshot. The API reads the existing direct
connector callback cache for `output_state_code_v2`,
`set_current_readback_v2`, `ocp_readback_v2`, and `protection_code`, and uses the
existing Native `get_state` route for `safety_lease_armed`. Each required
electrical callback must carry `esp_native_api` provenance, `SensorState` type,
and a present monotonic subscription timestamp no older than ten seconds. The
lease callback must independently carry Native provenance, `BinarySensorState`,
and a fresh callback timestamp. Fetch time is not a freshness source.

The existing `StartupRecovery.replay_deferred_startup_restore` runs beneath the
same app-scoped owner lock as normal START. For a quarantined candidate, it
reads the canonical document, validates candidate and canonical journals with
the existing `read_guard`, and delegates electrical validation to the existing
`assess_main_guard_before_output_on`. It rechecks canonical session ID, battery
ID, and Guard revision after the assessment before exposing the diagnostic
result as `last_guard_assessment`.

The assessment branch always returns without session restore or activation,
including when the synthetic result is `RECONCILED`. The candidate remains
quarantined, controller remains inactive, and canonical file bytes stay
unchanged. Missing direct callbacks, bad identity/revision, invalid Guard,
unproven lock/lease, stale telemetry, protection faults, and Iset/OCP mismatch
all block; each blocked reason is recorded in the retained candidate's
in-memory `blocker`. Explicit START also refuses while a Guard candidate remains
quarantined; the Manual path was not changed. Emergency verified OFF retains
its independent route.

`GuardedRestoreCandidate.capture` now deep-copies the decoded document before
placing it behind its top-level `MappingProxyType`; later mutations to the
source's nested dictionaries cannot alter the candidate. No persistence schema,
stored bytes, or writer changed.

## Synthetic validation

- Focused Guard/Native/startup/START/restore/Manual set: **91 tests PASS** using
  the existing Python 3.12 `/home/home-pc/.venvs/pcp-test` environment.
- Coverage includes direct Native RECONCILED but still quarantined, HA-only
  rejection, stale callbacks and lease, protection fault, mismatched Iset/OCP,
  invalid Guard, canonical revision change, owner/lease rejection, nested
  candidate isolation, START quarantine, and existing Manual regressions.
- `python -m compileall -q .`: **PASS**.
- `git diff --check`: **PASS**.
- Outer canonical WSL Python 3.12 discovery with the existing project venv and
  synthetic `TG_TOKEN`: **2,472 tests, 3 skipped, PASS** in 105.899s.
  Full log: `/tmp/d123-s57-canonical.log`. The earlier bounded Codex run timed
  out before summary and is superseded by this canonical acceptance.

No physical acceptance is claimed. A source-only assessment cannot establish
the target ESP callback contract or activate a Guarded restore. The controller
candidate remains quarantined pending separately authorized live/physical
validation and an explicitly designed activation transaction.

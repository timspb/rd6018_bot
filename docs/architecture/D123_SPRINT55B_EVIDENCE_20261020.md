# D123 Sprint 55B evidence — 2026-10-20

## Scope and start

Source-only continuation on `codex/d118-start-lease-repair-20261019`, starting
from exact clean HEAD `134d777ae9b55a1a8c36646903a2c133f676dba7`. No node104,
ESP, HA, firmware, service, deployment, GitHub, or physical Output interaction
was performed. No dependencies, recipes, safety thresholds, lease behavior,
Manual behavior, OVP/OCP, or ESP priority were changed.

## Before and after inheritance graph

Before:

```text
ManagedChargeController
└── ProductionChargeController (empty production marker)

ProductionChargeController
└── AutoStrategyProductionChargeController (compatibility class)
    └── DiagnosticProductionChargeController
        └── MixActiveAuthorityMixin (MRO-first lifecycle owner)
```

The actual Python bases were
`DiagnosticProductionChargeController(MixActiveAuthorityMixin,
AutoStrategyProductionChargeController)` and
`AutoStrategyProductionChargeController(ProductionChargeController)`.

After:

```text
ManagedChargeController
└── ProductionChargeController (empty production marker)

AutoStrategyProductionChargeController = ProductionChargeController
DiagnosticProductionChargeController = ProductionChargeController
```

The two legacy names are aliases only and are not active classes or hosts.
Production bootstrap now constructs `ProductionChargeController` directly.
The `MixActiveAuthorityMixin` class no longer exists; `MixActiveTimeAuthority`
is a durable clock helper, not a controller base.

## Exact behavior moved

Removed all six remaining live diagnostic subclass declarations:
`__init__`, `battery_fault_assessment`, `update_diagnostic_context`,
`_refresh_stored_diagnostics`, `_update_live_diagnostic_evidence`, and
`_diagnostic_hv_veto`. `diagnostic_controller.py` now contains only the legacy
alias. `runtime.charge.diagnostics` owns diagnostic context initialization and
assessment update, stored SG refresh and deduplication, bank-fault evidence
update, and the pure HV veto. Existing application session/stage tick owners
sequence them against state fields on the one canonical controller host.
`apply_authoritative_stage_tick` still applies the veto before either
ENTER_DESULFATION or ENTER_MIX effect, so normal, fallback, and recovery paths
retain the veto-before-effect ordering.

Removed `MixActiveAuthorityMixin.__init__`, `_mix_authority_session_id`,
`_enter_mix`, and `try_restore_session`. Production extension initialization
explicitly creates the durable authority on the same host. Application session
orchestration starts its record on canonical MIX entry, observes active/inactive
time, and terminalizes timeout. Canonical ordinary restore still completes
first, then reconstructs MAIN Guard, then restores production extension state;
durable MIX restore is the last part of that existing extension restore. It
continues to validate session identity and preserve `COOLING` with
`source_stage=MIX`. Missing/invalid authority clears restored targets and rejects
restore fail-closed.

No second FSM/session state host, canonical persistence writer, or physical
execution owner was introduced. `ProductionChargeController` and
`AutoStrategyProductionChargeController` remain empty marker/compatibility
boundaries; they are the remaining P4 class-shape blocker.

## Architecture and verification

Added `tests/test_d123_sprint55b_architecture.py` to gate the non-host aliases,
same-host initialization, deleted mixin/subclass, veto-before-effect ordering,
and Guard -> production extension -> MIX restore order. Updated existing
diagnostic and legacy-preemption tests to patch/call the new runtime owner.

Using Python 3.12 from `/home/home-pc/rd6018-v3-deploy/.venv` with synthetic
`TG_TOKEN=123456789:d123` and `PYTHONPATH=tests`:

- Focused diagnostic, architecture, bank-fault, MIX authority, MIX timeout and
  legacy-preemption suites: **26 tests, PASS**.
- Broader Guard, production entrypoint, Manual, START, and final SAFE_WAIT batch,
  together with diagnostic/bank-fault/MIX integration suites: **96 tests PASS**.
  Two guessed module names in that command were absent from this checkout and
  produced import errors; those were not product-test failures.
- `python -m compileall -q .`: **PASS**.
- The canonical MIX authority path is derived when `MixActiveTimeAuthority` is
  constructed as `<runtime.charge.persistence.SESSION_FILE>.mix-authority.json`.
  Its document binds `version`, `session_id`, elapsed active seconds, active
  state, wall anchor, and optional terminal reason. `begin(session_id)` creates
  the record; restore calls `load(expected_session_id)` after ordinary restore
  and Guard reconstruction; live observation requires the same identity;
  terminalization records the reason and inactive state. Missing, malformed, or
  mismatched records remain a restore rejection.
- Test fixture migration: `ProductionControllerTests._restore_document` now
  writes a matching authority record for its explicit restored session ID;
  `_persist_runtime_signal` and `_persist_finish_state` bind records to their
  fixture controller's session and place them beside that test's session file;
  the legacy delta-marker fixture writes the matching record directly. Restored
  controllers attach to the isolated per-session authority path without
  overwriting the record. The live CC tick fixture initializes its own isolated
  authority record and stubs stored-SG lookup. The cooling MIX-clock fixture
  begins a matching record in a unique temporary location. No missing/mismatch
  rejection test was made permissive. The MIX-only diagnostic test now uses the canonical runtime diagnostic state, and HANDS_OFF release now expects the canonical recovery-trace session identity.
- Exact restore/cooling/storage batch after migration:
  `test_production_controller`, `test_production_cooling_contract`, and
  `test_done_storage_restore`: **39 tests PASS**.
- Wider requested focused batch covering those suites, MIX timeout and legacy
  preemption, diagnostics, Guard binding, production entrypoint, application
  ownership gates, START, final SAFE_WAIT, startup recovery, Manual, and
  recovery/Manual continuation: **126 tests PASS**.
- `python -m compileall -q .`: **PASS**.
- Outer canonical direct WSL Python 3.12 discovery with synthetic
  `TG_TOKEN=123456789:d123s55b` and `PYTHONPATH=tests`:
  **2,458 tests, 3 skipped, PASS**. The first outer full run exposed two stale
  fixtures only: MIX-only diagnostic veto still injected the retired
  `battery_fault_assessment` attribute, and HANDS_OFF release expected the
  retired `_mix_authority_session_id()` test hook. Both fixtures were migrated
  to the canonical diagnostic owner / trace session identity, focused 2/2
  passed, and the repeated full suite passed. Full log:
  `/tmp/d123-s55b-canonical.log`.
- P4 was analyzed but not continued into production configuration refactoring.
  `ProductionChargeController` still carries restore defaults and the
  `PRODUCTION_EXTENSION_HOST` switch used by host initialization and ordered
  restore. These are active configuration semantics, not an empty marker, so
  deleting that class is not the conditional safe cut described in the mission.
  `AutoStrategyProductionChargeController` is still a compatibility subclass.
  P4 remains open pending an explicit Managed host configuration migration and
  its consumer/test update.

## Remaining work

- **P4 not closable yet:** `ProductionChargeController` still carries production
  restore and initialization configuration; it is not only an empty marker.
  `AutoStrategyProductionChargeController` remains a compatibility subclass.
  Closing P4 requires moving those settings to explicit canonical Managed host
  configuration and updating its consumers without creating another host.
- **P2 partial:** MAIN Guard restore admission and remaining raw canonical
  session document/audit lifecycle ownership remain deferred. Guard restoration
  ordering remains fail-closed and is not weakened here.
- **P5 open:** complete canonical discovery, Python 3.10/3.11/3.12 matrix,
  exact source release gates, and later supervised physical acceptance. This
  sprint performs no physical validation and authorizes no deployment.

No service/deployment or hardware action was authorized or attempted.

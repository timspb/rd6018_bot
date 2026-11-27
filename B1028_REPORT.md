# B1028 — D145 source-paired observer ABI compatibility audit

Run: `rd6018-b1028-20261126-r73-d145-abi-parity`
Requested source HEAD: `170aa91a7e7d8bc578f5dfa32d7fea12f411f9fa`
Branch: `codex/rd6018-b1028-d145-abi-parity-20261126`
Initial worktree: clean.

## Result

**No current D145/D144/D149 software callback ABI defect found. No production source changes.** The exact offline fixtures passed. D145’s existing entrypoint is still pinned to the historical D146 source/profile and cannot admit this candidate; do not repin it in this audit. Candidate readiness and the safe source-freeze/profile/read-only-proof handoff are in [`docs/acceptance/B1028_D145_OBSERVER_ABI_READINESS.md`](docs/acceptance/B1028_D145_OBSERVER_ABI_READINESS.md).

The current callback contracts are internally compatible:

- D144 calls its evidence provider with keyword `require_stopped` at PRE_STOP (twice), STOPPED, POST_START, and recovery boundaries.
- D145 adapts that established engine argument to the D090 owner reader’s `require_service_stopped` keyword. The owner proof callback itself remains a no-argument callable, as required by D090.
- D149’s router is that no-argument callable. PRE_STOP chooses D147; STOPPED and POST_START choose D150 in ordinary mode; RECOVERY chooses D151 and sets `D090_STATE_PRESERVING_RECOVERY=1`. D145 software replacement explicitly uses the state-preserving D151 route for every execute boundary, including PRE_STOP, so state/quarantine preservation does not depend on whether `charge_session.json` exists.
- The phase adapter checks the expected stopped flag before reading each proof; D144 also verifies the exact four-call sequence after `run()`. A one-off fake-owner probe deliberately supplied a STOPPED proof at PRE_STOP and confirmed rejection before `run()`, with the original callback and lock restored. Unknown phases, proof schema drift, invalid/reused source nonces, changed observer bytes, or unsafe observer paths fail closed.
- Execute and recovery save the original `owner.proof` and restore it in `finally`, including proof exceptions. Recovery selects `RECOVERY` before invoking the fresh recovery reader.

The historical installed `validate_physical_off(..., allow_active_session=...)` signature mismatch documented in `docs/operations/D149_PHASE_AWARE_PHYSICAL_PROOF.md` remains a source-pairing concern: the current tracked D090 validator accepts that keyword, while a historical installed module may not. The audited owner must use one exact source-paired D090/D144/D145 set. This audit does not add a fallback that could mask a mixed installation.

Current policy is unchanged: OVP/OCP and raw R16=1/2 are observable/operator-managed only; they do not trigger automatic software or ESP STOP, admission checks, or threshold programming. R16=3 and unknown nonzero, measured V/I and temperature paths, R18, and the existing ESP-local 900-second lease remain the independent safety paths. No physical observations or acceptance are claimed.

## Exact offline evidence

Project venv: `/home/home-pc/.venvs/pcp-test/bin/python` (Python 3.12.3), with `PYTHONPATH=.:tests:tools`.

```text
PYTHONPATH=.:tests:tools /home/home-pc/.venvs/pcp-test/bin/python -m unittest \
  tests.test_node104_d145_entrypoint \
  tests.test_d144_owner_binding \
  tests.test_d149_observer_router

Ran 31 tests — OK (exit 0, 0.684 s)
```

The parser’s expected usage error in `test_cli_exposes_only_d145_transaction_phases` is asserted by the fixture; the test suite completed successfully. Fixtures use temporary files, fake owner/service objects, and a fake observer runner. They perform no node, network, ESP/HA, service, actuator, or device operation. A separate ad hoc fake-owner probe for stale PRE_STOP phase evidence also passed; it was not counted among the 31 unittest cases.

## Scope delta from historical D146 pin

The local Git object for old D146 source `d351c208cbf8666f881a4660df6a0b211170e857` is present. Comparing it with the requested source HEAD yields **1,008 files changed, 113,355 insertions, 15,797 deletions**. This is the broad accumulated branch delta and is not a D145-only diff. The release/observer-specific changed paths in that delta are:

- Added: `tools/d144_owner_binding.py`, `tools/d144_state_preserving_transition.py`, `tools/d149_observer_router.py`, `tools/node104_d145_entrypoint.py`.
- Modified: `tools/node104_d090_release.py`, `tools/node104_d090_transaction.py`.
- Added focused runbooks: `docs/operations/D145_OWNER_EXECUTION_RECOVERY.md`, `docs/operations/D149_OBSERVER_ROUTING_REVISION_2026-11-17.md`, `docs/operations/D149_PHASE_AWARE_PHYSICAL_PROOF.md`.

The old entrypoint pin identifies D146 source `d351c208cbf8666f881a4660df6a0b211170e857`, preimage `9651e979e6394fd53ee373010f845ba00e7ccbbfa85a7a313b95893a0edea444`, and a historical profile digest. Those values are historical evidence only. No current installed node values were inferred.

## Limits and status

P0–P9 remains **98/103**. Three P3 physical gates and two P8 physical/release gates remain **HOLD**. The B1023 profile skeleton remains invalid. No D090 transition, service action, deployment, firmware operation, live physical proof, or source admission was performed.

Only this report and `docs/acceptance/B1028_D145_OBSERVER_ABI_READINESS.md` are intended changes. Shared checkpoint/master/handoff/runbook are left untouched for controller reconciliation. No staging, commit, push, network/GitHub, node104, ESP, HA, RD6018, firmware, service, Output/setpoint, lease, or original dirty worktree action occurred. R7.3 completion callback remains launcher-owned.

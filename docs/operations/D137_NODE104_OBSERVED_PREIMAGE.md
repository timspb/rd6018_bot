# D137 — independent observed preimage for next node104 software release

Captured 2026-10-31 by `tools/d137_observed_preimage.py --pid 162141` on node104. Read-only. Independent of the legacy D090 `STARTED` transaction.

## Acceptance result

- Schema: `D137_OBSERVED_PREIMAGE_V1`; phase `OBSERVED_PREIMAGE`; `candidate=null`; `admitted=false`.
- Composite preimage SHA-256: `f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c`.
- Installed app: 1194 files; tree SHA-256 `691e3ffd0b612d6832e8cd95030196f42ac384138c68ffd6b1e3545d85afd669`.
- Installed venv: 10175 entries, 9335 regular files, 4 symlinks; tree SHA-256 `17797cd36bea1633c6ff6efda05e4ab8c450d9369c12cec828f30217c4d72cf5`.
- Live PID: `162141`; verified `/opt/services/rd6018-bot/app/bot.py` process identity.
- Historical D090: transaction `818df047a6e64a22905d6da900162a86`, phase `STARTED`, candidate inventory missing.
- Original D090 journal SHA-256 `030f0b7aae43402f523bb57f5acd606e3ab2fe4f7c7d4efd40258b40bde8014e`.
- Original deploy-marker SHA-256 `0d96a7d51ad6216a5c7bd12b1987a1c2ca5468f2facc8fd1f497e4260787632f`.
- Retired session ID `e18eb85b81b44aeabd1eb7b29443594c`; verified-OFF evidence `execution-port-off:1793374858315444915`.
- Session journal SHA-256 `4ff32ed675343c0dbb96c6fcc7b60eeb1a47e503ab09403d88205e7fc7ace1c0`.
- Quarantine journal SHA-256 `e3f2b92e9b3dbec03d86f601f71ae8ac90db58dd0d50eb73747c38f519edc30c`.
- Four isolated tests on node104: 4/4 PASS. No service or hardware operations.

## Interpretation and next release boundary

This is a new *observed source-of-bytes* baseline, not a reconstruction of D090 candidate venv evidence, not a Git commit release identity, and not a deploy authorization.

Any subsequent software release needs an independent transaction owner that:
1. Validates this composite preimage against live bytes and the exact running process before changing anything.
2. Preserves live `state/` and durable retired session/quarantine identity through installation and rollback. Never copies D090 historical `state/` over it.
3. Binds a new candidate to a reproducible release source archive, complete staged app+venv inventories, current service/firmware/lease protection, and fresh device safety evidence.
4. Maintains its own separate transaction ledger; never writes the legacy D090 record or silently upgrades the old `.deploy_sha` based on a composite source tree.
5. Fail-closes before service stop on any missing candidate artifact, drift, identity mismatch, or insufficient OFF proof.

The release machinery is **not yet authorized to activate**. The next legitimate milestone is to pair this observed preimage with a new verified release candidate and an owner-tested state-preserving transition. Do not use the historical D090 `recover` as a ledger cleanup operation.

Safety: no Output ON, setpoint, OVP/OCP, or 900-second lease changes.

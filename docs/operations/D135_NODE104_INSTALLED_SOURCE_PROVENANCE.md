# D135 — node104 installed app provenance, source-only reconciliation

Captured 2026-10-31 using a read-only SHA-256 inventory of the 1,194 regular files in `/opt/services/rd6018-bot/app`, independently copied to HOME-PC as `d134_node_app_inventory.json`. No remote application files or state were modified.

## Complete source correspondence

The exact candidate commit recorded in the historical D090 journal is `930239c670899e14ccb09154d99baf77df90da10`.

- **1,186 / 1,194** installed files correspond in content to this candidate commit.
- **8 / 1,194** differ from the candidate and have exact Git object-content hashes matching current GitHub `main` (including `f2a272432194d7a3f34c06314e36ad22edb02b97` and predecessor commits).
- **0 files** are absent from candidate commit, **0 candidate files** are missing on node104.
- No unknown installed application source was identified.

Eight later source replacements, all identical to GitHub `main`:

1. `application/controller_session_retirement.py`
2. `application/execution_port.py`
3. `application/operator_recovery_clearance.py`
4. `application/start_transaction_runner.py`
5. `operator_managed_stop.py`
6. `rd_startup_authority.py`
7. `runtime/charge/lifecycle.py`
8. `runtime/charge/persistence.py`

Comparison procedure: list files by relative path from the installed node; hash each on node104; export Git tree at `930239c`; compare Git byte hashes and (for Windows archive transport artifacts only) LF-normalized hashes. All 16 files originally reported as divergent from `main` matched the `930239c` Git blob SHA-256 **without** normalization; the eight later replacements matched `main` Git blobs **without** normalization. Windows `git archive` converted CRLF in many textual files, creating an initial false-positive divergence; do not treat this transport encoding as a node source change.

## Interpretation

Installed **source tree identity is now established as a precise, reproducible composition**: candidate commit `930239c` plus eight identified post-candidate replacements. It is not identical to any single commit. It is *not* a fully authenticated D090 candidate deployment because the exact candidate `venv/` inventory is still missing from the historical STARTED journal. The live installed `venv/` and old backup `venv/` cannot independently certify the missing candidate artifact.

The existing original D090 transaction remains `STARTED`, with `candidate_inventory` missing and marker `58321a866dd68195bf8264d1d9ebe7c18a60748f`. Current live session is durably `RETIRED`, quarantine false. Do not rewrite `.deploy_sha` to `930239c` or GitHub HEAD: either would mislabel the composite installation.

## Next bounded closure action

Search **external, immutable release/candidate artifacts** for an exact candidate venv attestation, without taking the running tree as ground truth. If none exists, retain the historical transaction and introduce a separate, explicitly named **observed composite baseline** that records current app + venv bytes without pretending it was D090's original candidate inventory. Preserve state; no `recover`, rollback, journal rewrite, service stop, Output ON, setpoint/protection changes, or lease change. The D090 source owner now has pre-stop rejection guards (D134).

Evidence is a forensic software inventory, not fresh ESP electrical OFF proof.

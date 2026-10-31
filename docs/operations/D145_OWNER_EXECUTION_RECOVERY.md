# D145 — shared-owner cutover and recovery wiring

2026-10-31. Source-only integration; **no node104 production cutover performed**.

D145 adds `execute_under_owner` and `recover_under_owner` to `tools/d144_owner_binding.py`. These functions accept the existing `D090Transaction` instance and hold its original `D090_TRANSACTION.lock` throughout their respective operations. There is no second service owner or independent production CLI.

## Execution

1. Enforce pinned production root, machine-verification callback, actual `SystemdService`, software release classification and reviewed source profile.
2. Under the common lock, invoke D144 prepare-only/D142: D137 installed preimage, D138 staged bytes/venv, D140 space gate, and independently fresh D091 Native/HA OFF.
3. Make an isolated durable same-filesystem candidate copy under `candidate-d144/`, verify exact source and venv inventories.
4. **Re-measure disk capacity after candidate copy** before any D144 journal or service stop; ensure full old app+venv backup plus reserved space remains available.
5. Invoke the D144 state-preserving transaction with its separate durable journal, exact old and new byte inventories, fresh per-boundary D090-owner physical proofs, and distinct candidate/restored service stability callbacks.
6. D144 stores installed release identity independently in `D144_INSTALLED_RELEASE.json`; historical D090 STARTED journal, old deploy marker, and `state/` remain unchanged.

## Recovery

`recover_under_owner` acquires the **same D090 lock**, reads only the D144 ledger, verifies the expected release identity, then delegates to D144 recovery with fresh owner recovery proofs. Historical `D090Transaction.recover()` is NOT invoked. State is not rolled back.

An interrupted `PREPARED` phase without any backup now settles as `RESTORED` **only** after the exact original installed app/venv bytes and running old service are positively verified. If stopped or drifted, it fails before any service operation.

## Testing and outstanding work

- **19/19 isolated tests PASS on node104**, exercising combined D144 engine + owner binding and crash recovery. No real service stops in the test suite.
- The physical/staged candidate baseline D138 is still `d351c208cbf8666f881a4660df6a0b211170e857`; its binary environment is staged separately. Original D137 preimage SHA-256 `f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c`.
- A production *entrypoint* and source-paired D124 software release profile for this specific composite preimage are not provided by D145. The existing D090 CLI cannot be repurposed to run this transition; doing so could consult the historical STARTED journal.
- End-to-end recovery using a stopped real `SystemdService`, immediately fresh ESP Native measurements, and a precise old/new release source profile is not yet accepted.
- The prepared D138 build predates D139–D145 commits; installing it would not install later deployment-tool changes. That is intentional only if the intended application version remains pinned to D138.

**Operational decision:** do not invoke a production cutover on node104 from this merge. New production activation requires an exact profile, a narrow supported CLI/operational entrypoint, and full real-system recovery testing. Never rewrite D090 to COMMITTED, delete the only rollback copy, or change Output, setpoints, OVP/OCP or the 900-second lease merely to pass admission.

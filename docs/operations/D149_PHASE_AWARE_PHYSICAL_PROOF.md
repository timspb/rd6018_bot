# D149 — phase-aware D147/D148 physical proof routing

The existing canonical D090Transaction remains the only transaction owner and lock owner. D149 adds `tools/d149_observer_router.py` and connects it to the D145 owner-driven execution and recovery paths.

**Execution phase order:** `PRE_STOP` twice (original D147 observer), `STOPPED` once (recovery-capable D148), `POST_START` once (D148). This order matches the four invocations in the existing D144 state-preserving engine. Any wrong stopped-service flag or extra callback fails closed. The original `owner.proof` callback is restored in `finally`.

**Recovery:** use only D148 in `RECOVERY` mode, with `D090_STATE_PRESERVING_RECOVERY=1`; all recovery calls revalidate SHA and receive fresh independent Native/HA nonces. The original owner callback is restored after recovery. D090 historical ledger and `state/` are unchanged.

**Source integrity:** each collection checks exact SHA-256 of pinned D147 `1127e9e3...` or D148 `a738f08e...`, verifies file permissions and parent path, schema equality to canonical D090 PhysicalOffProof, and independent nonces. The active service virtualenv is used so collection survives an app/venv swap; separate prior D148 probes confirmed candidate venv compatibility. The observer itself never changes charging settings or operates systemd.

On node104, **28/28 isolated D144/D145/D149 tests PASS**, using fixture services and directories only. No actual service stop, candidate activation or physical output operation performed.

Remaining production gates: exact D146 profile must be loaded into the owner, a narrow authenticated entrypoint must be implemented, rollback after actual systemd interruption must be demonstrated, and post-start physical readback must be accepted in the real service. D149 is source-only until then.

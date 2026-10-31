# D149 — phase-aware D147/D148 physical proof routing

The existing canonical D090Transaction remains the only transaction owner and lock owner. D149 adds `tools/d149_observer_router.py` and connects it to the D145 owner-driven execution and recovery paths.

**Execution phase order:** `PRE_STOP` twice (original D147 observer), `STOPPED` once (recovery-capable D148), `POST_START` once (D148). This order matches the four invocations in the existing D144 state-preserving engine. Any wrong stopped-service flag or extra callback fails closed. The original `owner.proof` callback is restored in `finally`.

**Recovery:** use only D148 in `RECOVERY` mode, with `D090_STATE_PRESERVING_RECOVERY=1`; all recovery calls revalidate SHA and receive fresh independent Native/HA nonces. The original owner callback is restored after recovery. D090 historical ledger and `state/` are unchanged.

**Source integrity:** each collection checks exact SHA-256 of pinned D147 `1127e9e3...` or D148 `a738f08e...`, verifies file permissions and parent path, schema equality to canonical D090 PhysicalOffProof, and independent nonces. The active service virtualenv is used so collection survives an app/venv swap; separate prior D148 probes confirmed candidate venv compatibility. The observer itself never changes charging settings or operates systemd.

On node104, **28/28 isolated D144/D145/D149 tests PASS**, using fixture services and directories only. No actual service stop, candidate activation or physical output operation performed.

At the time of the original D149 evidence, production gates still included source-paired entrypoint integration. D145 now provides that entrypoint and pins the tracked D146 profile. Actual stopped-service recovery/systemd interruption acceptance and post-start physical readback remain unproven. D149 routing is source-integrated; its recorded node observations are historical evidence and are not a current physical read.


## Additional live read-only observation

The D149 router was invoked on node104 using both `PRE_STOP` (D147) and `RECOVERY` (D148) with the real service Python environment. Both independently returned fresh HA102/ESP128 physical OFF, zero outputs, unarmed lease and two source nonces. The service stayed on PID `162141`.

The node104 *installed* legacy `node104_d090_release.validate_physical_off` does not accept the newer optional `allow_active_session` argument in GitHub main. This was discovered during the initial read-only probe; the probe was corrected to use the common validation interface because no active session existed. Therefore, do not launch recovery using the old installed D090 Python module; use the exact source-paired D145/D149 release owner and review the recovery signature before production cutover.

On node104, **29/29** isolated tests PASS after adding a negative test proving the owner callback and lock are restored following proof failure. Full CI matrix Python 3.10/3.11/3.12 PASS.
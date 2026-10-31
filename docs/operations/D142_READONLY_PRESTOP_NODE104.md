# D142 — Combined read-only pre-stop assessment, node104

2026-10-31. A single read-only invocation of `tools/d142_readonly_prestop.py` checked all four necessary evidence layers:

1. D137 installed composite preimage `f8fa701e7362490fcdf61c5e2ab84664c950f3599f56c7eb2477434b603f874c`, process PID 162141.
2. D138 source `d351c208cbf8666f881a4660df6a0b211170e857`, candidate identity `45b6ae0e2dc2f42ee76eaca8311178fd76f92e0254b63e60f3d7393ceee1979e`, complete isolated 3.11 venv and `pip check`.
3. D140 same-filesystem free capacity 1,029,730,304 bytes, with 571,887,616 bytes required for full rollback copy, overhead and 256 MiB reserve. `capacity_pass=true`.
4. **Fresh** D091 collector executed last; validated using canonical `node104_d090_release.validate_physical_off` with `require_service_stopped=False` and the observed process PID. Independent HA102 and ESP128 proved R18 OFF and both output voltage/current zero, physical owner count 1, no active session, Native freshness and safety lease disarmed. Firmware expectation explicitly `2.3-ha-canonical`; edge lease TTL checked by D091.

Result: `D142_READONLY_PRESTOP_V1`, `PASS_AT_OBSERVATION_ONLY`, `activation_authorized=false`.

Six isolated tests on node104 **6/6 PASS** covering valid proof and refusal of stale, wrong-PID, output-current, duplicated-nonce and armed-lease evidence.

The proof is transient and not a durable permission or a substitute for the immediately-before-stop recheck. Code does not stop/restart services, switch app/venv, write state, journal, marker, or operate charging hardware. User's lease remains 900 s.

**Remaining production work:** canonical D090 still has historical `STARTED` transaction `818df047a6e64a22905d6da900162a86` with absent candidate inventory. D139 is an offline fixture, not a production transition. A new owner-supported, state-preserving deployment with a separate ledger, complete rollback evidence, crash recovery and fresh pre-stop physical revalidation has not been implemented/activated. The D138 source also predates later repository changes, so the intended deployed release must be explicitly pinned to those reviewed bytes; do not silently treat D138 as current GitHub HEAD.

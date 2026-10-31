# D148 — pinned recovery observer and candidate-runtime compatibility

2026-10-31. Target D138 source `d351c208cbf8666f881a4660df6a0b211170e857`; historical D090 remains STARTED.

## Verified read-only matrix on node104

All probes used independently fresh ESP Native SensorState callbacks and HA sensor observations; no actuator writes or service restarts.

- D138 candidate D091 collector (SHA-256 `a738f08e5554fa70188af856bc359b198838a983394948aaee8c64fdd9df1e95`), candidate Python 3.11 venv, **current** installed runtime: PASS in state-preserving recovery mode, Output OFF, U=0, I=0, lease unarmed.
- Same D138 collector, same candidate venv, **D138 candidate runtime source tree** (tested using a throwaway read-only script whose only changes redirected the app imports and config to staged `tree/`): PASS; independent Native+HA readings zero and Output OFF.
- Original D147 pinned collector (SHA-256 `1127e9e3ba52a43ca97ddd8501ea4ac9a52887e708d725fd1299fd22d15a2398`), candidate venv, D138 candidate runtime source tree: PASS with independent Native+HA readings zero and Output OFF.
- D147 original collector on current runtime: previously PASS with physical OFF.

These are read-only compatibility tests against the *currently running* bot (PID 162141); they do **not** claim that a new systemd service has been started, or prove stopped-service behavior.

## D148 artifact

`tools/d148_recovery_collector.py` creates an exact SHA-pinned copy of the D138 recovery-capable D091 collector at `/opt/services/rd6018-bot/d147-proof/d148_recovery_d091_collector.py`, outside swappable `app/`. Installation is host-bound, demands the original D147 pin remain unchanged, uses O_EXCL, and fsyncs before verifying the new copy. The original D147 collector is never overwritten.

Five isolated node104 tests PASS: exact byte copy, idempotence, changed source refusal, tampered D147 refusal, corrupt existing copy refusal, symlink destination refusal (one combined case).

The D148 collector supports `D090_STATE_PRESERVING_RECOVERY=1`: unlike D147, it can preserve state documents while requiring physical OFF and fresh Native/HA evidence.

## Remaining deployment boundary

The owner must deliberately select the D148 frozen collector for recovery (and revalidate it on every collection), retain D147 for unchanged baseline observations, verify the required firmware and source SHA, and use the correct current Python runtime. A stored observer snapshot is not itself a successful recovery or an authorization to turn Output ON. The historical D090 journal and 900-second lease are unchanged. There has been no production cutover.

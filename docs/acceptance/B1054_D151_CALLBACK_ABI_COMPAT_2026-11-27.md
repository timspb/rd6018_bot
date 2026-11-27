# B1054 — D151 Native callback ABI compatibility (source-only)

**Date:** 2026-11-27  
**Source baseline:** installed B1053 code commit `656463fd1e6473708ecddeb0f4e3e0c17a878db4`, active on node104 in D144 slot23 COMMITTED.  
**Issue:** [#184](https://github.com/timspb/rd6018_bot/issues/184).  
**Scope:** SOURCE-ONLY. No deployment, charger command, ESP flash, lease change, reboot, service stop/start or D144 journal write in this B1054 stage.

## Reproduced failure and bounded fix

The original SHA-pinned D151 collector (`9500454a068d120f0b23740ad3933eb70ebd8cf24fbaa7c03ddafd3e729cb8d9`) installs a temporary one-argument observer `observe(state)`. Modern `ESPHomeTransport._ensure_state_subscription()` invokes `_on_state(state, connection_generation=..., source_client=...)`, so the original D151 collector fails with `TypeError: observe() got an unexpected keyword argument 'connection_generation'`. This was seen on real node104 during B1053 D145 POST_START; a one-time historical-transport read-only bridge was used only to reconcile slot23 to COMMITTED. It was not a permanent source fix.

This B1054 change adds a single `_dispatch_subscribed_state` seam in `runtime/physical/transports/esp128.py`: reject old connection-generation callbacks or a foreign client before invoking any observer; use `inspect.signature` to recognize only the original one-positional `observe(state)` legacy shape, forwarding just `state` in that case. Current D091 callbacks with `connection_generation` and `source_client` still receive both original provenance arguments. Unsupported callback signatures fail closed. In particular, a callback-internal `TypeError` is **not caught and retried**, avoiding double effects and masking errors. No change to `_on_state` native cache semantics, hardware write/Output owner, source of timestamps, safety lease or firmware.

## Validation

- `tests/test_b1054_d151_callback_compat.py` contains eight direct fake-ESP Native subscription scenarios: old D151 one-arg typed SensorState, stale generation rejection, foreign client rejection, reconnect with unchanged legacy wrapper, current D091-style metadata forwarding, unsupported callback ABI, internal TypeError not swallowed/retried, and foreign client same-generation rejection.
- Combined native/transport/D091/D106/D145/D149 release and output receipt cohort: **159 tests PASS** with candidate Python 3.11.18; the expected argparse negative-case stderr in D145 tests is not a failing test. `git diff --check`: PASS.
- Additionally ran the **actual original D151 module copied read-only from node104**, verified its exact SHA, and called its unmodified `_fresh_measured_sensor_callbacks` against B1054 ESPTransport on a patched fake `aioesphomeapi` APIClient: typed `SensorState` R18=OFF, measured current=0 A, callback acquisition and source metadata all PASS. **This is simulated transport integration, not a fresh physical hardware observation.**
- **Not run:** physical ON/OFF, setpoint programming, protection trips, 900 s lease expiry, P3 supervision, P8 DR. Canonical P0–P9 remains **99/104** (P3 three HOLD, P8 two HOLD). B1053 on node104 remains the unchanged COMMITTED installed version. Subsequent software release needs new exact SHA, CI, preflight, and normal D145 transaction if desired.

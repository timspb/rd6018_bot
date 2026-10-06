# ERADICATION-09 compatibility source reference

Captured before final compatibility-source deletion on 2026-10-06.

These files were already unreachable from the production composition graph before
deletion. Git history remains the authoritative source archive; the blob IDs below
pin the exact final reference content.

| Retired source | Git blob | Last source commit before retirement | Canonical replacement |
| --- | --- | --- | --- |
| `auto_manual_off_v2.py` | `1ba39984fa6482eef16a983a44aea30efd7cc634` | `8a7bec1312bf8fc3d41977af2e7a6a527b3dee94` | direct Manual-OFF inertness in V2 controller + external terminal condition |
| `done_storage_restore.py` | `bc02509dafc47d9524257aaab4771252a271aa3f` | `0d9dc707469f689e35e0ccbdd2aac932a2e51e22` | `runtime.charge.persistence`, controller state and production restore guards |
| `live_output_readback_v2.py` | `b352978a7fa958842368c1c2f454331185e492dc` | `058fddca1227ac9c5388057e784c7f6cf2185a58` | `rd6018_telemetry.canonicalize_live()` |
| `production_guardrails_v2.py` | `445ced9335b248a9b8a45df78faea48ecc91a75f` | `0d9dc707469f689e35e0ccbdd2aac932a2e51e22` | `runtime.production_runtime` + `runtime.charge.runtime.cooling_guard` |
| `soft_watchdog_containment.py` | `ed1914f35d9bf4f680aa18f1066ef6f29c494074` | `a4907a1231b050d7d3b956f28ee5694df0c3fe5e` | `runtime.safety.soft_watchdog` + canonical runtime watchdog loop |
| `telegram_startup_resilience.py` | `42d9b0ca5095351056e227777fd899e5bc599958` | `7f7ddd0793291159454a1c1c2fc0927a794ee114` | `telegram.runtime.ResilientBootstrapBot` |

Deletion criterion: zero production import reachability plus canonical replacement
coverage and full regression suite PASS. No VM104 or hardware mutation is part of
this archive operation.

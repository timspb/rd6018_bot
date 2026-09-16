# RD6018 Legacy Route Inventory

Status: Phase 1 classification. No route is removed here.

| Surface | Classification | Reason |
|---|---|---|
| `bot.py` | KEEP | production entrypoint |
| `v2_bootstrap.py` | KEEP | current composition root and V2 owner wiring |
| V2 controller, FSM, safety and output chain | KEEP | current execution authority |
| `ProductionManualSessionManager` | KEEP | current Manual session authority |
| V2 transaction owner and adapters | KEEP | rollback-compatible START owner |
| `/start` and dashboard compatibility | KEEP | production operator surface |
| `bot_legacy.py` | DEPRECATE | preserved rollback/emergency runtime |
| `v2_bot_ui` direct START handlers | DEPRECATE | transitional route; must remain available for rollback until parity is proven |
| `runtime/v2_runtime.py` Telegram/program handlers | DEPRECATE | legacy UI/runtime path with actuator-capable call sites |
| `start_custom_charge` compatibility adapter | DEPRECATE | legacy bridge into the managed Manual path |
| duplicate v1 UI installers and quick parsers | DEPRECATE | compatibility-only surfaces |
| unused `runtime/physical/*` production surfaces | REMOVE LATER | remove only after import and reachability proof |
| `physical_test_control*.py` from production composition | REMOVE LATER | move to explicit bench/tools boundary after test coverage is preserved |
| orphan migration copies and duplicate config sources | REMOVE LATER | cleanup only after canonical contracts exist |

`DEPRECATE` means “no new callers; preserve for rollback”. `REMOVE LATER`
requires route reachability evidence, parity tests, rollback validation and an
explicit review.

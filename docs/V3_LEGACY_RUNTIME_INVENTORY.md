# Retired runtime compatibility inventory

Status: **retired / removal evidence**.

The former runtime compatibility module is no longer part of the tree.

Removed surfaces:
- `bot_legacy.py`;
- `runtime/v2_runtime.py`;
- top-level `v2_startup.py`;
- `application/v2_start_runner_adapter.py`;
- `application/legacy_actuator_boundary.py`.

Production imports `runtime.production_runtime` directly and `bot.py` owns the
single composition lifecycle. The legacy module is quarantined from production
imports by removal, not by a forwarding facade.

Historical `v2_*` names that still exist are implementation/naming debt only.
They remain current production code where callers still depend on them; each
must be renamed or absorbed through ordinary caller migration, not by adding a
new compatibility facade.

ACTIVE START is fail-closed through current preflight, execution and verified
OFF containment. Retired activation-policy or runtime-facade layers must not be
reintroduced.

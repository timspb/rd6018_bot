# D068b — Guard transaction owner-lock and native telemetry correction

Source-only gate. No node104 deployment, no hardware commands, no charging recipe changes.

## Fixed defects

1. D066 accepted any supplied asyncio.Lock, so a caller could serialize only its own Guard transaction while the real production controller/manual/start/recovery paths ran in parallel. The ExecutionPort now starts with its guard owner lock UNBOUND. The transaction rejects a missing or foreign lock. An explicit bind_guard_owner_lock() hook is available for the future proven canonical lifecycle lock; it refuses silent rebind to a different lock. Production does NOT yet call the hook.
2. The original Guard readback check accepted only _meta.age_s, but the canonical Home Assistant freshness model uses last_reported, falling back to last_updated or age_s. The Guard now uses telemetry_freshness across native Output register 18, current, programmed Iset, OCP and protection registers, while explicitly requiring source metadata and rejecting age/skew violations. Legacy value mirrors do not substitute for V2 readbacks.

## Tests

Existing D066 transaction and negative fault tests plus new tests for unbound lock, foreign lock, refused rebind, real ISO last_reported with no age_s, stale/skewed heartbeat. The GH CI and local full-suite results must be recorded separately; no PASS should be assigned until execution completes.

## Remaining work, unchanged

This is NOT a completed owner-wide lock. The actual application must prove that the *same* bound lock covers 30-second tick, session persistence, all start/restore/manual/lifecycle paths and physical output commands without a nested deadlock or guard bypass. A loaded guard from charge_session.json must be reconciled against fresh native Iset/OCP and verified Output before any ON; pending transactions and inconsistent source state must fail closed. Do not create a new lock per operation or call binding a substitute for coverage.

D061 adopted-child SIGKILL remains physical HOLD; D063 naturally observed EFB/Ca/Ca SAFE_WAIT remains open; physical trial ceiling 15.5 V; AGM and existing MIX recipes untouched.

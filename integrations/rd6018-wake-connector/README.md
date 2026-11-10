# RD6018 Wake R7.2 connector (standalone package)

This package is an isolated, read-only event bridge. It does not import the RD6018 production runtime, access actuator APIs, change RD6018 state, or share its service lifecycle. Deploy it as a separate service only after the producer transport gate below is closed.

## Audit result and transport gate

The repository's D106 collector (`tools/node104_d106_live_observer.py`) performs a fresh HA REST + typed ESP Native read, but also refuses an active persistent charge session; it is a strict Output-OFF proof collector, not a live-charge telemetry feed. D151 is the same D091 read-only proof family, selected by D149 for state-preserving release/RECOVERY. Neither is suitable as a periodic active-charge source. This connector therefore accepts only a strict, bounded snapshot document from a separately reviewed read-only source adapter. That adapter must be implemented against the existing node104 diagnostic interface that is admitted for live charging; this repository/session has not exposed such an interface.

The only concrete shared-launcher R7.2 call found is the completion-only `notify_r72_complete.py` invocation (`--route`, `--run-id`, Codex exit code and report). It cannot carry independent RD6018 events and must not be used here. The current MCP tool list exposes no general submit or ACK lookup API. Consequently the outbox holds events when no supported producer is injected. It reports status as `submitted` or `acknowledged` only when the injected producer explicitly returns that state. A bridge enqueue receipt is not delivery ACK.

**Not deployable/activatable yet:** live-charge read-only source adapter, supported R7.2 generic producer and ACK contract are unresolved. No endpoint, server, direct database write, or fake completion semantics are implemented.

## Event and storage contract

`connector.py` contains strict normalization, route validation, bounded persistent SQLite outbox, dedupe by stable event ID, age/size limits and capped retry backoff. Fields pass an allowlist (stage, fault/status labels, voltage/current/temperature and freshness); raw source payloads, credentials and arbitrary text never pass to the bridge. Route configuration is read dynamically from a root-owned mode-0600 JSON file; missing/invalid route holds local events. Never put route IDs in command-line arguments or logs. Rotate the route by atomically replacing the config file with a freshly supplied current-chat route, then restart/reload only this separate connector after production activation is authorized. Do not infer a route from recency or any other chat.

Snapshot schema accepted by `normalize_snapshot`:

```json
{"schema":1,"captured_at":1794300000.0,"state":{"source":"esp_native_api","values":{"stage":"MAIN","voltage_v":14.2,"current_a":3.1,"freshness_s":2.0}}}
```

The source adapter must attest to the source through its reviewed output contract; the connector itself does not trust a process merely because it prints `esp_native_api`.

## Configuration and local checks

Copy `config.example.json` to a protected runtime location, set mode 0600, provide a current route only at activation time, and use a private outbox path. No route is included in this repository. `config.schema.json` declares bounds. The systemd template is separate from `rd6018-bot.service`, runs under a dedicated unprivileged account with filesystem/network restrictions, and is not enabled by this source change.

Tests are isolated/mocked and never contact R7.2, SSH, HA or ESP. Run from this package with `python3 -m unittest -v test_connector.py`.

## Activation checklist (not authorization)

1. Review and add a live-charge-safe read-only source adapter using the installed, supported diagnostic interface; prove it cannot write and emits fresh typed Native evidence.
2. Obtain the R7.2 owner's documented producer API, least-privilege auth, per-event idempotency, submitted-vs-ACK behavior and safe ACK query. Add a mocked adapter and tests. Do not reuse completion hooks or write route databases.
3. Install this package independently with a dedicated account, config 0600, outbox 0600, pinned host key if SSH is part of the approved adapter, and systemd resource limits. Do not touch `rd6018-bot.service`, its files or state.
4. Run dry-run/read-only source proof first; then ask the owner for separate activation authorization. Do not run while the current charge is active until the independent source contract is proven harmless.
5. Verify one newly generated connector event through `wake_r72_inspect_this_chat` on the exact current chat route before claiming delivery. Never replay a submission whose status is unknown.

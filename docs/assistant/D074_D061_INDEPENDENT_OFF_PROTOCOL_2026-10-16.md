# D074 — independent D061 OFF adapter boundary

**Status: OFFLINE SOFTWARE ONLY. Physical D061 adopted-child SIGKILL remains HOLD.**

This source change adds tools/acceptance_guard/independent_off_protocol.py plus fault-injection tests. It has no deployed writer, production caller, systemd unit, endpoint connection, credential loading or live Output command.

## Contract

The independent root-owned supervisor must retain its lock FD independently of the child (D061 fixture PR #93). Its separately credentialed emergency OFF adapter cannot depend on the bot's HA session, locks or event loop. Every injected callback receives ONE absolute monotonic deadline, at most 45 seconds from entry. Network transports must enforce their own socket deadlines. An unbounded blocking synchronous callback cannot be interrupted by asyncio.wait_for.

A successful OFF command ACK is not electrical proof. Two different native producers must return fresh post-command Output OFF, near-zero current/voltage and NORMAL protection. Their physical_producer_id and path_id must both differ. Two HA proxies of the same ESPHome Modbus reading have the same physical producer lineage and are NOT independent. Missing, stale, conflicting or non-native reports yield HOLD, with no lease-disarm call.

Only after independent OFF proof may the edge lease be disarmed. A third independent producer must report fresh DISARMED before the same deadline. Failure, timeouts, unverified or duplicated sources can never become LEASE_DISARMED. The receipt distinguishes off_independently_proved from lease_independently_disarmed.

## Actual physical blockers

Historical docs/V3_LIVE_TRANSPORT_SMOKE_TEST.md identified HA102 REST 192.168.1.102:8123 and ESP128 native API 192.168.1.28:6053, with unavailable HA states and unreachable direct ESP in the previous smoke. This is not current node104 connectivity proof. A new network-only node104 endpoint check was denied by remote command policy (exit 126); no workaround was attempted.

Current read-only node104 shows root-owned 0600 global D061 acceptance lock, but NO independent supervisor unit/process. The normal bot and D063 observer remain active. The missing separately credentialed native OFF command/readback route is therefore a HARD HOLD before any real adopted PB_MANAGED child SIGKILL with Output ON.

Source-only work cannot establish the required <=45 second electrical OFF latency; existing edge lease TTL remains 900 seconds. Do not deploy or activate D061 based on unit tests. No firmware, AGM, MIX recipes, MAIN Guard actuation or node104 services changed. Physical voltage ceiling remains <=15.5 V until separately authorized.
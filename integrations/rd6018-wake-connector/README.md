# RD6018 event producer

This package prepares RD6018 events for the universal Event Gateway. The dedicated Wake Bridge 7.2 project chat owns the Gateway, Dispatcher, and R7.2 transport adapter. This repository implements only the producer envelope, source adapter seam, and a bounded local spool.

## Responsibility boundary

- RD6018 owns its event semantics and emits `rd6018-node104` events.
- The Gateway owns destination policy and configuration, durable dispatch, deduplication, retries, acknowledgements, and quarantine after Gateway submission.
- The Gateway transport adapter owns the connection to the existing supported ingress.
- This producer has no chat route IDs, destination selection, delivery retry policy, ACK interpretation, R7.2 internals, or Codex completion semantics.

The source adapter performs independent Home Assistant REST `GET /api/states/{entity_id}` calls only. It does not import the production `HA102` transport and has no POST, service-call, WebSocket, switch, or number-entity path. Its sensor allowlist is read from the canonical `config/physical/ha102.yaml`; only `sensor.*` and `binary_sensor.*` are accepted. It does not access ESP Native API or node104.

HA credentials are supplied only as `RD6018_WAKE_HA_URL` and `RD6018_WAKE_HA_TOKEN`. There is no fallback to `HA_TOKEN`. Configure them through the service manager's protected environment injection (the template uses a root-owned mode-0600 EnvironmentFile outside the repository). The token never belongs in connector JSON, process arguments, logs, events, or exceptions. Use a dedicated non-admin HA user and group with `POLICY_READ` only for the exact allowlisted sensor entities, and no `POLICY_CONTROL` or `POLICY_EDIT`. Do not use an owner/admin token. See [Home Assistant authorization](https://developers.home-assistant.io/docs/auth_permissions/).

The client validates an HTTP(S) base URL, validates every entity ID against a sensor-only regex and explicit allowlist, rejects duplicate IDs, verifies TLS certificates by default, refuses redirects (so the bearer token cannot be forwarded to another host), uses a five-second request timeout, and caps responses at 64 KiB. Implausible numeric values are rejected rather than clamped. `last_reported` provides freshness when available. If absent, `last_updated` is a conservative fallback and freshness is explicitly unknown when neither timestamp is present. Internal and external temperatures have separate fields; internal temperature is never substituted for missing external temperature.

`charge_session.json` is read-only, bounded to 64 KiB, opened as a no-follow regular file, and parsed only for known stage/profile and `main_current_guard_v1` schema fields. Files older than the configured `session_max_age_s` (default 24 hours; bounded to 60 seconds–7 days) are ignored. Only allowlisted guard fault categories are emitted. Session/battery IDs, raw documents, guard internals, and arbitrary strings are discarded.

## Event contract

Each event has exactly this semantic shape:

```json
{
  "event_id": "uuid",
  "source": "rd6018-node104",
  "event_type": "charger.heartbeat",
  "severity": "info",
  "occurred_at": "2026-11-10T14:00:00Z",
  "payload": {},
  "schema_version": 1
}
```

`event_id` is a deterministic UUIDv5 from the source, event type, and occurrence identity. It remains stable across process restarts; a new occurrence identity yields a new UUID. Heartbeats use interval-slot identity and report a successful telemetry snapshot, not that the RD6018 output is enabled. Timestamps must be RFC3339 UTC. Event type and severity are allowlisted. Payload fields are allowlisted and bounded; internal and external temperatures remain separate. Secrets, tokens, routes, session and battery IDs, raw guard documents, logs, and personal data are excluded.

The proposed types are `charger.fault`, `charger.stage_changed`, `charger.mode_changed`, `charger.telemetry_stale`, `charger.telemetry_unknown`, `charger.telemetry_recovered`, `charger.guard_fault`, `charger.guard_state_unknown`, `charger.guard_recovered`, `charger.service_down`, `charger.service_recovered`, `charger.heartbeat`. `charger.overtemperature` is intentionally excluded until an independent sensor source and threshold policy are proven.

## Local spool and Gateway seam

SQLite stores bounded events with `pending_gateway`, `gateway_accepted`, or `quarantined_unknown` state. Persistent event IDs prevent the same occurrence being enqueued again after restart. `gateway_accepted` means only that the Gateway client reported acceptance; it does not mean a destination received the event. An unknown result is quarantined and is not submitted again automatically. There is no Gateway delivery retry or ACK workflow here.

`EventGatewayClient.submit(event: EventEnvelope) -> GatewayAcceptance` is a proposed injectable Python protocol only. The Gateway API contract is not finalized. No HTTP transport is implemented. Endpoint, method, authentication, headers, credential injection names, response semantics, and idempotency behavior remain intentionally unspecified. Future endpoint and credential values must be injected using the Gateway owner's published contract; do not add them to RD6018 config before that contract exists.

Configuration contains local entity/session paths and bounded spool settings. There is no route or credential field. `config.example.json` is illustrative; the connector is not installed or activated by these source changes. The Gateway producer remains unwired until its generic producer and ACK contract is published; no real producer is currently connected.

## Integration checklist after Gateway API publication

1. Confirm the Gateway owner's exact endpoint, method, auth injection, request schema, and response contract.
2. Confirm event idempotency and the meaning of accepted and unknown outcomes.
3. Implement only an `EventGatewayClient` adapter against that published contract; keep route selection, retries, ACK orchestration, and R7.2 details in Gateway services.
4. Add mocked producer tests for the published contract, including timeout/unknown behavior. Do not simulate final chat delivery.
5. Review the independent source adapter and payload policy. Do not deploy or activate from this checklist.

## Local tests

Run from this directory with `python -m unittest -v test_connector.py`. Tests use temporary files and mocked HTTP transport; they do not contact HA, ESP, node104, the Gateway, or Wake Bridge.


Installation precondition: before any future deployment, grant the dedicated service user read-only access to charge_session.json through a narrow group/ACL. Do not make this file world-readable or change production file permissions as part of this source task.


## Node104 read-only observer (2026-11-10)

observer.py is a separate, read-only runtime observer. It does not use the HA REST adapter above and does not issue Modbus, ESP Native, HA service, RD6018 setpoint, output, OVP/OCP, or control commands. It reads only:

- /opt/services/rd6018-bot/state/rd6018.db using SQLite mode=ro (latest sensor sample and recovery stage);
- the bounded session_recovery_quarantine.json and rd_control_mode_v2.json state documents;
- rd6018-bot.service state and its journal.

The observer does not read or publish battery/session identifiers, raw journal lines, arbitrary state documents, credentials, or HA entity IDs. Its allowlisted payload contains measured voltage/current/external temperature, output state, charging stage, control mode, service state, guard state, freshness and a normalized fault code.

### Notification policy

- Critical guard/service/error transitions are sent immediately.
- A persistent quarantine is sent once per entry; repeats are suppressed. Recovery is a separate immediate event.
- A repeated log error is suppressed while it continues; a new occurrence is eligible after 30 minutes without that code.
- Charging-stage and control-mode changes are sent immediately.
- Telemetry loss/unknown and recovery are sent on transition, not every poll.
- Polling is 20 seconds; this is internal observation only and does not create chat messages.
- Summary/parameter events are emitted at startup and then no more often than every 1800 seconds (30 minutes), including a status-only summary if telemetry is stale.

### Gateway transport

The dedicated producer token is injected through /etc/rd6018-wake-observer.env (root-owned, mode 0600), never through the JSON config, command line, event payload or logs. The observer posts only to the universal Gateway's documented /v1/events endpoint using the rd6018/node104 producer identity. The Gateway alone owns route selection and R7.2 delivery. HTTP 202 is considered accepted only when the returned event ID matches and queue_state is queued; 429 and connection refusal remain pending, while uncertain outcomes are quarantined and not blindly retried.

The Gateway listener is bound only to VM110's private LAN address 192.168.1.110; no public listener or firewall exposure is created. The producer binding is maintained in R7.2, not in this repository.

The observer service is rd6018-wake-observer.service. Its spool and state live under /var/lib/rd6018-wake-observer, separate from the charger database. Keep the charger service and its safety lease untouched.


### Deployment status — 2026-11-10

The observer code, configuration and systemd unit are staged on node104 and pass the offline startup check. The universal Gateway on VM110 listens on 192.168.1.110:8765; node104 has verified TCP connectivity and HTTP /healthz returns 200. The R7.2 producer binding for rd6018/node104 already points to the current chat route.

Activation: observer service is enabled and active on node104. The existing producer credential was transferred in memory from VM110's protected Gateway environment over the pinned D061 SSH connection into root-owned /etc/rd6018-wake-observer.env (mode 0600); the token is not stored in this repository or chat. The observer reaches the private Gateway at 192.168.1.110:8765 and receives HTTP 202 acceptance. The guard-read isolation defect was fixed: only CAP_DAC_READ_SEARCH is granted, unreadable guard state is explicit unknown, and unknown can never emit recovery. Current live snapshot correctly reports guard_state=quarantined and fault_code=guard_readback_fault. Gateway acceptance is confirmed, but R7.2 host receipt/ACK remains HOLD (last_ack=null); do not replay events with unknown_host_receipt. Detailed evidence: reports/RD6018_OBSERVER_ACTIVATION_GUARD_READ_FIX_20261110.txt.

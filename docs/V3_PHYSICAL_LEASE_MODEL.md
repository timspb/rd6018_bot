# V3 physical bench lease

`BenchLeaseProvider` is a manual, operator-controlled authorization layer for
the first physical write phase. It is deliberately not the production edge
lease and has no scheduler, HA control path, Telegram handler or automatic
acquisition.

The only permitted scope is `DISABLE_OUTPUT_ONLY`. A lease for this scope can
never authorize enable, setpoint or protection-reset operations. Leases have a
finite duration, can be revoked by the operator and are recorded by
`LeaseAudit`.

## Execution order

```text
real operator
  -> BenchLeaseProvider.request(DISABLE_OUTPUT_ONLY)
  -> provider.validate(lease)
  -> Safety / envelope checks
  -> PhysicalExecutionGate.arm(operator)
  -> verified DISABLE_OUTPUT only
  -> fresh Output OFF + current=0 readback
  -> execution and lease audit
```

No synthetic lease is acceptable for a live run. `PhysicalExecutionConfig`
remains disabled by default. The async verified-off executor is the only new
execution entry point and does not expose enable, voltage, current or reset
operations.

## Parameters and access

The default lease duration is configured at provider construction (`300 s`),
not in the production runtime. Physical endpoint and secret references remain
in `config/physical/ha102.yaml` and `config/physical/esp128.yaml`; see
`docs/V3_LIVE_TRANSPORT_SMOKE_TEST.md` for the access map and credential
loading order.

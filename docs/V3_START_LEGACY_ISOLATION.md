# START isolation contract

Status: **current**.

Production START has one route:
`ProductionStartRouteAdapter -> StartPreflightService -> ApprovedStartPlan ->
ProductionStartExecutionPort -> ProductionStartRunner ->
StartTransactionRunner -> application.start_transaction_service`.

Retired compatibility modules `bot_legacy.py`, `v2_startup.py` and
`application.v2_start_runner_adapter.py` are absent.

Direct UI/controller/HA START fallbacks are forbidden. Capacity input and quick
start both submit through the same production route. DRY_RUN and SHADOW are
explicit diagnostic modes only; they are not alternate production owners.

The canonical transaction service owns verified physical START and failed-start
OFF containment. No second START owner or compatibility facade may be added.

# RD6018 UI adapter boundary — Phase 8.3

## Responsibility

`OperatorUIAdapter` is a shadow-only input boundary. It accepts an operator
command, validates its format, creates an `OperatorIntent`, and returns an
operator diagnostic result. It does not dispatch the intent.

Supported commands:

- `START PROFILE CAPACITY_AH`;
- `STOP`;
- `PAUSE`;
- `RESUME`;
- `STATUS`.

`STATUS` is represented by the existing read-only `REFRESH_PANEL` intent. The
adapter does not decide whether a start is safe or allowed.

## Correlation

Each result carries a `trace_id`. The corresponding `DiagnosticEvent` carries
the same trace through `TraceCorrelation`, so UI acceptance/rejection can be
joined to later application and execution observations without placing a UI
object into the domain.

## Forbidden dependencies

The adapter does not import or call:

- `ChargeEngine` or `SessionManager`;
- safety or controller code;
- HA, ESPHome, RD transport or physical adapters;
- production Telegram handlers;
- persistence or production composition.

The returned `OperatorIntent` remains a request. A separate application layer
must decide whether and how to process it.

## Rollout boundary

This phase adds only contracts and a shadow parser. Production Telegram,
START, ACTIVE, HA, ESP and physical execution are unchanged.

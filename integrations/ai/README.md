# Optional RD6018 AI integration

This package owns the AI-specific implementation: DeepSeek client, system and
user prompt preparation, context/history/trend projection, strategy/hold snapshot
formatting, and AI Telegram dialog and analysis-screen presentation. Its runtime
adapter receives the production namespace and existing read owners; it does not
own charge decisions, event history, physical execution, Output, setpoints,
protection, or leases.

Core application, charge, Telegram routing, and production-runtime imports do
not import this package. AI-specific paths load it only when composed or called.
Without a configured API key, the dialog reports unavailable before requesting
context; without `aiohttp`, the client reports unavailable before any network
request. The optional client has no physical command path.

Compatibility exports remain at `ai_engine.py`, `ai_system_prompt.py`,
`application.operator_snapshot_provider`, `runtime.production_runtime`,
`runtime.charge.diagnostics`, `application.production_session_extensions`,
`charge_controller`, and the former runtime UI analysis modules where existing
callers still use them. These are dispatch boundaries only.

TODO: review AI analytics/prompt quality separately. Review UNKNOWN Output
formatting only within this optional AI presentation path; UNKNOWN must not be
converted into confirmed Output OFF evidence or used by non-AI control/UI.

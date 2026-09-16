# V3 hardware capability and battery safety envelope

The envelope is an additional, data-only compatibility check before the
execution policy and physical gate. `BatterySafetyEnvelope` declares the
allowed chemistry, capacity range and charge limits. `HardwareSafetyEnvelope`
declares voltage/current/power limits, supported modes and capabilities.

`EnvelopeValidator` checks requested V/I, power, chemistry, mode and profile.
It never clamps values or changes a recipe. It returns `ALLOWED` or
fail-closed `BLOCKED` with violated limits and reproducible evidence. A
blocked result is rejected by `PhysicalExecutionGate`; warnings, if added in
future, remain non-authorizing until an explicit policy defines them.

The intended bench order is: discovery, read snapshot, envelope validation,
safety preflight, manual ARM, then the existing gated executor. No automatic
execution or production integration was added.

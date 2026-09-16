# V3 multi-transport read-only model

`PhysicalTransportFactory` creates `HA102Transport` or `ESPHomeTransport`
from the validated `runtime.config` bundle. Hostnames, ports, entity/object
mapping and secret environment-variable names are configuration data; no
endpoint or credential is embedded in adapter code.

Both adapters expose discovery, health, capabilities and `HardwareSnapshot`
reads. HA uses the existing token environment reference and GET state
endpoints. ESPHome uses its encrypted native API and state subscription. The
only write exposed in the first physical phase is `DISABLE_OUTPUT`; it is
reachable only through the manually armed physical execution gate and must be
followed by fresh OFF and zero-current readback. Enable, setpoint and
protection-reset writes remain unsupported.

`PhysicalSnapshotComparator` compares common readback fields with a numeric
tolerance and reports `MATCH`, `MISMATCH` or `INCONCLUSIVE`. A future command
transport must remain behind the already-existing physical execution gate and
must not be inferred from this read-only layer.

# V3 multi-transport read-only model

`PhysicalTransportFactory` creates `HA102Transport` or `ESPHomeTransport`
from the validated `runtime.config` bundle. Hostnames, ports, entity/object
mapping and secret environment-variable names are configuration data; no
endpoint or credential is embedded in adapter code.

Both adapters expose discovery, health, capabilities and `HardwareSnapshot`
read operations only. HA uses the existing token environment reference and
GET state endpoints. ESPHome uses its encrypted native API and state
subscription. Neither adapter defines enable, disable, setpoint or reset
methods. Write capabilities are therefore reported as unsupported in this
phase.

`PhysicalSnapshotComparator` compares common readback fields with a numeric
tolerance and reports `MATCH`, `MISMATCH` or `INCONCLUSIVE`. A future command
transport must remain behind the already-existing physical execution gate and
must not be inferred from this read-only layer.

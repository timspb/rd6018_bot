# V3 human-readable configuration

The checked-in `config/` tree is non-secret, bilingual configuration. Physical
profiles identify the two discovered endpoints: HA `192.168.1.102:8123` and
ESPHome `192.168.1.28:6053`. The ESPHome profile requires encrypted API access
and names the environment variable `ESPHOME_API_KEY`; it does not contain the
key. HA similarly names `HA_TOKEN` without storing the token.

`runtime.config.load_config()` loads transport profiles, RD hardware limits,
charge data, safety limits and runtime policy into validated models. Numeric
RD limits are checked against the hardware envelope and errors identify the
field and unit. YAML loading has no side effects and does not construct a
transport, arm the physical gate or execute commands.

Charge and safety files are data sources for future consumers. Existing
runtime/recipe implementations remain unchanged in this phase; migration of
their hard-coded values is a separate, reviewed step. The V1 UI and production
actuator path are untouched.

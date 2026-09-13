# V3 configuration

All files in this directory are human-editable, non-secret configuration.
Comments are provided in Russian and English and include units where a value
has units. Secrets are referenced by environment-variable name only.

Load order: physical transport profiles, RD hardware envelope, charge data,
safety limits, then runtime policy. Validation must complete before a future
runtime consumer is constructed. Editing these files does not by itself
activate a transport or execute a physical command.

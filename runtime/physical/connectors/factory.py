from __future__ import annotations

from runtime.config import ConfigBundle

from .esp_direct import ESPDirectConnector
from .ha_esp import HAESPConnector


class PhysicalConnectorFactory:
    def __init__(self, config: ConfigBundle):
        self.config = config

    def create(self, name: str):
        definition = (self.config.connectors or {}).get(name)
        if not definition or not bool(definition.get("enabled", False)):
            raise ValueError(f"connector is not enabled: {name}")
        if name == "ha_esp":
            return HAESPConnector(self.config)
        if name == "esp_direct":
            return ESPDirectConnector(self.config)
        raise ValueError(f"unsupported connector: {name}")

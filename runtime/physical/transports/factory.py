from __future__ import annotations

from runtime.config import ConfigBundle

from .esp128 import ESPHomeTransport
from .ha102 import HA102Transport


class PhysicalTransportFactory:
    def __init__(self, config: ConfigBundle):
        self.config = config

    def create(self, name: str):
        profile = self.config.transports.get(name)
        if profile is None or not profile.enabled:
            raise ValueError(f"transport is not enabled: {name}")
        if profile.type == "home_assistant":
            return HA102Transport(profile, self.config.rd)
        if profile.type == "esphome":
            return ESPHomeTransport(profile, self.config.rd)
        raise ValueError(f"unsupported transport type: {profile.type}")

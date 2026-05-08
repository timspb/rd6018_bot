import importlib


def test_config_prefers_local_ha_url(monkeypatch):
    monkeypatch.setenv("HA_URL", "https://rd.timspb.ru:8123")
    monkeypatch.setenv("HA_LOCAL_URL", "https://192.168.1.102:8123")
    monkeypatch.setenv("HA_PREFER_LOCAL", "1")

    import config

    importlib.reload(config)

    assert config.HA_URL == "https://192.168.1.102:8123"


def test_hassclient_disables_tls_verification_for_local_url():
    from hass_api import HassClient

    client = HassClient("https://192.168.1.102:8123", token="dummy")

    assert client._disable_tls_verify is True

import pytest


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path_factory, monkeypatch):
    """Keep `itqan login` credentials and ITQAN_* settings from the developer's
    machine out of every test."""
    monkeypatch.setenv("ITQAN_CONFIG_DIR", str(tmp_path_factory.mktemp("itqan-config")))
    monkeypatch.delenv("ITQAN_API_KEY", raising=False)
    monkeypatch.delenv("ITQAN_REGISTRY_URL", raising=False)

import pytest


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path_factory, monkeypatch):
    """Keep `itqan login` credentials and ITQAN_* settings from the developer's
    machine out of every test."""
    monkeypatch.setenv("ITQAN_CONFIG_DIR", str(tmp_path_factory.mktemp("itqan-config")))
    monkeypatch.delenv("ITQAN_API_KEY", raising=False)
    monkeypatch.delenv("ITQAN_REGISTRY_URL", raising=False)
    # The opt-out variables, so the usage-header tests see the default.
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("ITQAN_NO_TELEMETRY", raising=False)

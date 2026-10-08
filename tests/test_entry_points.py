"""The CLI's command names."""

from importlib.metadata import entry_points


def test_console_scripts_where_installed_should_offer_itqan_and_itqan_cli():
    # Arrange / Act
    scripts = {ep.name: ep.value for ep in entry_points(group="console_scripts") if ep.value.startswith("itqan_cli")}

    # Assert
    assert scripts == {"itqan": "itqan_cli.main:cli", "itqan-cli": "itqan_cli.main:cli"}

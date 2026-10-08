"""`itqan login` / `logout` and the saved API key."""

import os
from pathlib import Path
import stat
import sys

from click.testing import CliRunner
import pytest
import responses

from itqan_cli import credentials
from itqan_cli.main import cli

REGISTRY = "https://registry.example"
OTHER_REGISTRY = "https://staging.registry.example"
KEY = "prefix.secret"

OPEN = {
    "slug": "mushaf-madinah",
    "name": "Mushaf Madinah",
    "category": "mushaf",
    "is_open_access": True,
    "access": "open",
    "access_request_url": None,
    "publisher_name": "Publisher",
    "languages": [{"language": "ar", "is_source": True, "latest_version": "1.0.0"}],
}


def _mock_me(status: int = 200) -> None:
    body = {"name": "Dev", "email": "dev@example.com"} if status == 200 else {"error_name": "authentication_required"}
    responses.add(responses.GET, f"{REGISTRY}/packages/me/", json=body, status=status)


def _mock_catalog(results: list[dict], **kwargs) -> None:
    responses.add(
        responses.GET, f"{REGISTRY}/packages/", json={"results": results, "count": len(results)}, status=200, **kwargs
    )


def _run(*args: str, input: str | None = None):
    return CliRunner().invoke(cli, list(args), input=input)


# --- credentials ----------------------------------------------------------------


def test_save_api_key_where_two_registries_should_keep_one_key_each():
    # Arrange / Act
    credentials.save_api_key(REGISTRY + "/", KEY)
    credentials.save_api_key(OTHER_REGISTRY, "other-key")

    # Assert
    assert credentials.load_api_key(REGISTRY) == KEY
    assert credentials.load_api_key(OTHER_REGISTRY) == "other-key"
    assert credentials.load_api_key("https://unknown.example") is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_save_api_key_where_saved_should_be_readable_only_by_owner():
    # Arrange / Act
    path = credentials.save_api_key(REGISTRY, KEY)

    # Assert
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_load_api_key_where_file_is_corrupt_should_raise():
    # Arrange
    credentials.credentials_path().parent.mkdir(parents=True, exist_ok=True)
    credentials.credentials_path().write_text("not json")

    # Act / Assert
    with pytest.raises(credentials.CredentialsError):
        credentials.load_api_key(REGISTRY)


# --- login / logout -------------------------------------------------------------


@responses.activate
def test_login_command_where_key_accepted_should_save_it():
    # Arrange
    _mock_me(200)

    # Act
    result = _run("login", "--registry-url", REGISTRY, input=f"{KEY}\n")

    # Assert
    assert result.exit_code == 0, result.output
    assert "Logged in to https://registry.example as Dev <dev@example.com>" in result.output
    assert KEY not in result.output  # the prompt hides the key
    assert responses.calls[0].request.headers["X-API-Key"] == KEY
    assert credentials.load_api_key(REGISTRY) == KEY


@responses.activate
def test_login_command_where_key_rejected_should_not_save_it():
    # Arrange
    _mock_me(401)

    # Act
    result = _run("login", "--registry-url", REGISTRY, "--api-key", KEY)

    # Assert
    assert result.exit_code == 1
    assert "did not accept that API key" in result.output
    assert credentials.load_api_key(REGISTRY) is None


@responses.activate
def test_login_command_where_registry_cannot_check_keys_should_save_with_warning():
    # Arrange
    _mock_me(404)

    # Act
    result = _run("login", "--registry-url", REGISTRY, "--api-key", KEY)

    # Assert
    assert result.exit_code == 0, result.output
    assert "saving it unverified" in result.output
    assert credentials.load_api_key(REGISTRY) == KEY


def test_logout_command_where_key_saved_should_remove_it():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)

    # Act
    result = _run("logout", "--registry-url", REGISTRY)
    again = _run("logout", "--registry-url", REGISTRY)

    # Assert
    assert "Removed the saved key" in result.output
    assert "No key saved" in again.output
    assert credentials.load_api_key(REGISTRY) is None


# --- the saved key is used ------------------------------------------------------


@responses.activate
def test_browse_command_where_key_saved_should_send_it(tmp_path: Path):
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_catalog([OPEN])

    # Act
    result = _run("browse", "-m", str(tmp_path / "m.yaml"), "--registry-url", REGISTRY, "--json")

    # Assert
    assert result.exit_code == 0, result.output
    assert responses.calls[0].request.headers["X-API-Key"] == KEY


@responses.activate
def test_browse_command_where_env_key_set_should_override_saved_key(tmp_path: Path, monkeypatch):
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    monkeypatch.setenv("ITQAN_API_KEY", "env-key")
    _mock_catalog([OPEN])

    # Act
    result = _run("browse", "-m", str(tmp_path / "m.yaml"), "--registry-url", REGISTRY, "--json")

    # Assert
    assert result.exit_code == 0, result.output
    assert responses.calls[0].request.headers["X-API-Key"] == "env-key"


@responses.activate
def test_browse_command_where_key_saved_for_other_registry_should_send_no_key(tmp_path: Path):
    # Arrange
    credentials.save_api_key(OTHER_REGISTRY, KEY)
    _mock_catalog([OPEN])

    # Act
    result = _run("browse", "-m", str(tmp_path / "m.yaml"), "--registry-url", REGISTRY, "--json")

    # Assert
    assert result.exit_code == 0, result.output
    assert "X-API-Key" not in responses.calls[0].request.headers

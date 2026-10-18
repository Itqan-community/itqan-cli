"""Tests for the usage-attribution headers sent with every request."""

from importlib.metadata import version
import os
from pathlib import Path
import uuid

import pytest

from itqan_cli import usage
from itqan_cli.credentials import config_dir

USER_AGENT = f"itqan-cli/{version('itqan-cli')}"


def _id_file() -> Path:
    return config_dir() / "install-id"


def test_install_id_where_first_run_should_create_a_uuid4_file():
    # Act
    install_id = usage.install_id()

    # Assert
    assert install_id is not None
    assert uuid.UUID(install_id).version == 4
    assert _id_file().read_text(encoding="utf-8").strip() == install_id


def test_install_id_where_file_exists_should_reuse_it():
    # Arrange
    existing = str(uuid.uuid4())
    _id_file().parent.mkdir(parents=True, exist_ok=True)
    _id_file().write_text(existing + "\n", encoding="utf-8")

    # Act / Assert
    assert usage.install_id() == existing
    assert usage.install_id() == existing


@pytest.mark.parametrize("content", [b"not-a-uuid", b"", b"\xff\xfe\x00garbage"])
def test_install_id_where_file_is_corrupt_should_regenerate_it(content: bytes):
    # Arrange
    _id_file().parent.mkdir(parents=True, exist_ok=True)
    _id_file().write_bytes(content)

    # Act
    install_id = usage.install_id()

    # Assert
    assert install_id is not None
    assert uuid.UUID(install_id).version == 4
    assert _id_file().read_text(encoding="utf-8").strip() == install_id


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs POSIX permissions, not root")
def test_install_id_where_file_is_unreadable_should_regenerate_it():
    # Arrange
    _id_file().parent.mkdir(parents=True, exist_ok=True)
    _id_file().write_text(str(uuid.uuid4()), encoding="utf-8")
    _id_file().chmod(0)

    # Act
    install_id = usage.install_id()

    # Assert
    assert install_id is not None
    assert _id_file().read_text(encoding="utf-8").strip() == install_id


def test_install_id_where_path_is_a_directory_should_return_none():
    # Arrange: can't be read, and can't be replaced by a file either.
    _id_file().mkdir(parents=True)

    # Act / Assert
    assert usage.install_id() is None


def test_install_id_where_config_dir_cannot_be_written_should_return_none(monkeypatch, tmp_path: Path):
    # Arrange: the config dir's parent is a regular file, so mkdir fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("ITQAN_CONFIG_DIR", str(blocker / "itqan"))

    # Act / Assert
    assert usage.install_id() is None


def test_install_id_where_write_fails_should_leave_no_temp_files(monkeypatch):
    # Arrange
    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(usage.os, "replace", fail)

    # Act
    assert usage.install_id() is None

    # Assert
    assert list(config_dir().iterdir()) == []


@pytest.mark.parametrize("var", ["DO_NOT_TRACK", "ITQAN_NO_TELEMETRY"])
@pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
def test_telemetry_disabled_where_opt_out_set_should_be_true(monkeypatch, var: str, value: str):
    monkeypatch.setenv(var, value)

    assert usage.telemetry_disabled() is True


@pytest.mark.parametrize("value", ["", "0", "false", "False", " 0 "])
def test_telemetry_disabled_where_opt_out_unset_or_falsy_should_be_false(monkeypatch, value: str):
    monkeypatch.setenv("DO_NOT_TRACK", value)
    monkeypatch.setenv("ITQAN_NO_TELEMETRY", value)

    assert usage.telemetry_disabled() is False


def test_usage_headers_where_outside_a_command_should_send_user_agent_and_install_id_only():
    # Act
    headers = usage.usage_headers()

    # Assert
    assert headers["User-Agent"] == USER_AGENT
    assert headers["X-Itqan-Install-Id"] == usage.install_id()
    assert "X-Itqan-Command" not in headers


@pytest.mark.parametrize("var", ["DO_NOT_TRACK", "ITQAN_NO_TELEMETRY"])
def test_usage_headers_where_opted_out_should_send_only_user_agent_and_create_no_file(monkeypatch, var: str):
    # Arrange
    monkeypatch.setenv(var, "1")

    # Act
    headers = usage.usage_headers()

    # Assert
    assert headers == {"User-Agent": USER_AGENT}
    assert not _id_file().exists()


def test_usage_headers_where_install_id_cannot_be_stored_should_still_send_user_agent(monkeypatch, tmp_path: Path):
    # Arrange
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("ITQAN_CONFIG_DIR", str(blocker / "itqan"))

    # Act
    headers = usage.usage_headers()

    # Assert
    assert headers["User-Agent"] == USER_AGENT
    assert "X-Itqan-Install-Id" not in headers


def test_install_id_file_should_not_be_world_writable():
    usage.install_id()

    if os.name == "posix":
        assert _id_file().stat().st_mode & 0o022 == 0

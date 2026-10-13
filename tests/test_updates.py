"""Telling users that newer versions of their installed assets exist: the notice
after `itqan install`, and `itqan outdated`."""

import json
from pathlib import Path

from click.testing import CliRunner
import pytest
import responses

from itqan_cli.lockfile import AssetLockfile, LockfileEntry, serialize_lockfile
from itqan_cli.main import cli

REGISTRY = "https://api.itqan.dev/api"
DOWNLOAD = "https://cdn.itqan.dev/assets/tafsir.csv"


@pytest.fixture(autouse=True)
def _notice_on(monkeypatch):
    monkeypatch.delenv("ITQAN_NO_UPDATE_NOTICE", raising=False)


def _project(tmp_path: Path, *, locked: str | None = "1.0.0") -> Path:
    """A manifest with `hafs-tafsir: ^1.0.0`, locked to ``locked`` (no lockfile when None)."""
    (tmp_path / "itqan-assets.yaml").write_text('schema_version: 1\n\nassets:\n  hafs-tafsir:\n    version: "^1.0.0"\n')
    if locked is not None:
        lockfile = AssetLockfile(
            lockfile_version=1,
            manifest_schema_version=1,
            assets={"hafs-tafsir": LockfileEntry(slug="hafs-tafsir", constraint="^1.0.0", version=locked)},
        )
        (tmp_path / "itqan-assets.lock").write_bytes(serialize_lockfile(lockfile))
    return tmp_path


def _mock_resolve(resolved: str = "1.0.0", **extra) -> None:
    result = {
        "slug": "hafs-tafsir",
        "asset_version_id": 7,
        "resolved_version": resolved,
        "asset_name": "Hafs Tafsir",
        "download_url": DOWNLOAD,
    }
    responses.add(
        responses.POST, f"{REGISTRY}/packages/resolve/manifest/", json={"results": [result | extra]}, status=200
    )
    responses.add(responses.GET, DOWNLOAD, body=b"surah,ayah,text\n", status=200)


def _run(project: Path, command: str, *extra: str):
    return CliRunner().invoke(
        cli,
        [
            command,
            "-m",
            str(project / "itqan-assets.yaml"),
            "-l",
            str(project / "itqan-assets.lock"),
            "--registry-url",
            REGISTRY,
            *extra,
        ],
    )


@responses.activate
def test_install_command_where_lockfile_fresh_should_send_manifest_range_as_constraint(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve()

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    body = json.loads(responses.calls[0].request.body)
    assert body["assets"]["hafs-tafsir"] == {"version": "1.0.0", "constraint": "^1.0.0"}


@responses.activate
def test_install_command_where_newer_version_in_range_should_suggest_install_force(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.2.0", latest_version="1.2.0")

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "1 asset has a newer version within your manifest's range: run `itqan install --force`" in result.output
    assert "outside" not in result.output


@responses.activate
def test_install_command_where_newer_version_beyond_range_should_suggest_outdated(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.0.0", latest_version="2.0.0")

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "1 asset has a newer version outside your manifest's range: run `itqan outdated`" in result.output
    assert "within" not in result.output


@responses.activate
def test_install_command_where_up_to_date_should_print_no_notice(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.0.0", latest_version="1.0.0")

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "newer version" not in result.output


@responses.activate
def test_install_command_where_registry_reports_no_latest_versions_should_print_no_notice(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve()

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "newer version" not in result.output


@responses.activate
def test_install_command_where_locked_version_withdrawn_should_only_warn_once(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(withdrawn=True, withdrawal_reason="Errors", latest_in_range="1.2.0", latest_version="1.2.0")

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "was withdrawn" in result.output
    assert "newer version within" not in result.output


@responses.activate
def test_install_command_where_update_notice_disabled_should_print_no_notice(tmp_path: Path, monkeypatch):
    # Arrange
    monkeypatch.setenv("ITQAN_NO_UPDATE_NOTICE", "1")
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.2.0", latest_version="2.0.0")

    # Act
    result = _run(project, "install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "newer version" not in result.output


@responses.activate
def test_outdated_command_where_newer_versions_exist_should_print_table(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.2.0", latest_version="2.0.0")

    # Act
    result = _run(project, "outdated")

    # Assert
    assert result.exit_code == 0, result.output
    header, row = result.output.splitlines()
    assert header.split() == ["Entry", "Installed", "In", "range", "Latest"]
    assert row.split() == ["hafs-tafsir", "1.0.0", "1.2.0", "2.0.0"]
    assert len(responses.calls) == 1  # resolves, downloads nothing
    assert not (project / "assets").exists()


@responses.activate
def test_outdated_command_where_json_should_print_updates_as_json(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.2.0", latest_version="1.2.0")

    # Act
    result = _run(project, "outdated", "--json")

    # Assert
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"name": "hafs-tafsir", "installed": "1.0.0", "in_range": "1.2.0", "latest": "1.2.0"}
    ]


@responses.activate
def test_outdated_command_where_up_to_date_should_say_so(tmp_path: Path):
    # Arrange
    project = _project(tmp_path)
    _mock_resolve(latest_in_range="1.0.0", latest_version="1.0.0")

    # Act
    result = _run(project, "outdated")

    # Assert
    assert result.exit_code == 0, result.output
    assert "All assets are up to date." in result.output


def test_outdated_command_where_no_lockfile_should_ask_to_install_first(tmp_path: Path):
    # Arrange
    project = _project(tmp_path, locked=None)

    # Act
    result = _run(project, "outdated")

    # Assert
    assert result.exit_code == 1
    assert "run `itqan install` first" in result.output

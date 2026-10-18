"""`itqan install` draws download progress only in a terminal."""

from pathlib import Path

from click.testing import CliRunner
import pytest
import responses

from itqan_cli import progress
from itqan_cli.downloader import AssetDownloader
from itqan_cli.exceptions import DownloadError
from itqan_cli.main import cli

REGISTRY = "https://api.itqan.dev/api"
URL = "https://cdn.itqan.dev/assets/quran.pdf"
BODY = b"%PDF-1.4 dummy pdf bytes"
SUMMARY = "  * quran-uthmani-hafs [2.4.1]: downloaded -> "


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "itqan-assets.yaml").write_text(
        'schema_version: 1\n\nassets:\n  quran-uthmani-hafs:\n    version: "^2.1.0"\n'
    )
    responses.add(
        responses.POST,
        f"{REGISTRY}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "quran-uthmani-hafs",
                    "asset_version_id": 10,
                    "resolved_version": "2.4.1",
                    "asset_name": "Quran Hafs",
                    "download_url": URL,
                }
            ]
        },
    )
    responses.add(responses.GET, URL, body=BODY, headers={"Content-Length": str(len(BODY))})
    return tmp_path


@pytest.fixture
def terminal(monkeypatch):
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setenv("COLUMNS", "120")
    monkeypatch.setattr(progress, progress._stdout_is_terminal.__name__, lambda: True)


def _install(project: Path, *extra: str):
    args = ["-m", str(project / "itqan-assets.yaml"), "-l", str(project / "itqan-assets.lock")]
    return CliRunner().invoke(cli, ["install", *args, "--registry-url", REGISTRY, *extra])


@responses.activate
def test_install_command_where_not_a_terminal_should_print_plain_lines(project: Path):
    # Act
    result = _install(project)

    # Assert
    assert result.exit_code == 0, result.output
    assert "\r" not in result.output
    assert SUMMARY in result.output


@responses.activate
def test_install_command_where_in_a_terminal_should_draw_progress_then_the_summary_line(project: Path, terminal):
    # Act
    result = _install(project)

    # Assert
    assert result.exit_code == 0, result.output
    drawn = result.output.index("\r(1/1) quran-uthmani-hafs [2.4.1]  [")
    cleared = result.output.index("\r" + " " * 10)
    assert drawn < cleared < result.output.index(SUMMARY)
    assert f"{len(BODY)}/{len(BODY)} B  100%" in result.output


@responses.activate
def test_install_command_where_no_progress_given_should_not_draw_progress(project: Path, terminal):
    # Act
    result = _install(project, "--no-progress")

    # Assert
    assert result.exit_code == 0, result.output
    assert "\r" not in result.output
    assert SUMMARY in result.output


@responses.activate
def test_install_command_where_asset_is_cached_should_not_draw_progress(project: Path, terminal):
    # Arrange
    _install(project)

    # Act
    result = _install(project)

    # Assert
    assert result.exit_code == 0, result.output
    assert "\r" not in result.output
    assert "cached (up-to-date)" in result.output


@responses.activate
def test_install_command_where_download_fails_midway_should_clear_progress_before_the_error(
    project: Path, terminal, monkeypatch
):
    # Arrange
    def fail_midway(self, asset, *, force=False, on_progress=None):
        on_progress(10, 100)
        raise DownloadError("connection reset")

    monkeypatch.setattr(AssetDownloader, AssetDownloader.materialize_asset.__name__, fail_midway)

    # Act
    result = _install(project)

    # Assert
    assert result.exit_code != 0
    assert not (project / "itqan-assets.lock").exists()
    cleared = result.output.rindex("\r")
    assert result.output[cleared - 1] == " "  # the bar was blanked out
    assert result.output.index("Error: connection reset") > cleared

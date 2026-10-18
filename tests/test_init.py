"""`itqan init`: write a starter itqan-assets.yaml from the live catalog."""

from pathlib import Path
import re

from click.testing import CliRunner
import pytest
import requests
import responses
from responses import matchers

from itqan_cli import browse, main
from itqan_cli.main import cli
from itqan_cli.manifest import parse_manifest_content

REGISTRY = "https://cms.itqan.dev"

MULTILINGUAL = {
    "slug": "tafsir-jalalayn",
    "name": "Tafsir al-Jalalayn",
    "category": "tafsir",
    "is_open_access": True,
    "publisher_name": "Publisher",
    "languages": [
        {"language": "ar", "is_source": True, "latest_version": "2.4.0"},
        {"language": "en", "is_source": False, "latest_version": "1.3.0"},
    ],
}
SINGLE = {
    "slug": "mushaf-madinah",
    "name": "Mushaf Madinah",
    "category": "mushaf",
    "is_open_access": True,
    "publisher_name": "Publisher",
    "languages": [{"language": "ar", "is_source": True, "latest_version": "1.0.0"}],
}
TRANSLATION_ONLY = {
    "slug": "true",
    "name": "Only a translation",
    "category": "translation",
    "is_open_access": True,
    "publisher_name": None,
    "languages": [{"language": "fr", "is_source": False, "latest_version": "0.2.0-beta.1"}],
}


def _mock_catalog(results: list[dict], *, query: dict | None = None) -> None:
    responses.add(
        responses.GET,
        f"{REGISTRY}/packages/",
        json={"results": results, "count": len(results)},
        status=200,
        match=[matchers.query_param_matcher(query or {"page_size": "50", "open_access": "true"})],
    )


def _uncomment(text: str) -> str:
    """The manifest as it reads once the user uncomments every example entry."""
    return re.sub(r'^  # ("|  )', r"  \1", text, flags=re.MULTILINE)


def _init(project: Path, *extra: str):
    return CliRunner().invoke(
        cli, ["init", "-m", str(project / "itqan-assets.yaml"), "--registry-url", REGISTRY, *extra]
    )


@responses.activate
def test_init_command_where_catalog_has_assets_should_write_commented_entries_with_language_comments(
    tmp_path: Path,
):
    # Arrange
    _mock_catalog([SINGLE, MULTILINGUAL])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    text = (tmp_path / "itqan-assets.yaml").read_text()
    assert "# Tafsir al-Jalalayn — languages: ar (source, 2.4.0), en (1.3.0)" in text
    assert "# Mushaf Madinah — languages: ar (source, 1.0.0)" in text
    assert parse_manifest_content(text.encode()).assets == {}  # nothing installs until the user chooses
    manifest = parse_manifest_content(_uncomment(text).encode())
    assert manifest.assets_dir == "assets"
    assert list(manifest.assets) == ["tafsir-jalalayn", "tafsir-jalalayn-en", "mushaf-madinah"]
    assert manifest.assets["tafsir-jalalayn"].version == "^2.4.0"
    assert manifest.assets["tafsir-jalalayn"].language is None
    english = manifest.assets["tafsir-jalalayn-en"]
    assert (english.asset, english.language, english.version) == ("tafsir-jalalayn", "en", "^1.3.0")
    assert "Created" in result.output
    assert "itqan browse" in result.output
    assert "itqan install" in result.output


@responses.activate
def test_init_command_where_only_a_translation_is_available_should_set_its_language(tmp_path: Path):
    # Arrange
    _mock_catalog([TRANSLATION_ONLY])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    manifest = parse_manifest_content(_uncomment((tmp_path / "itqan-assets.yaml").read_text()).encode())
    entry = manifest.assets["true"]
    assert entry.language == "fr"
    assert entry.version == "0.2.0-beta.1"  # a prerelease is pinned exactly; ^ would never match it


@responses.activate
def test_init_command_where_assets_dir_given_should_write_it(tmp_path: Path):
    # Arrange
    _mock_catalog([SINGLE])

    # Act
    result = _init(tmp_path, "--assets-dir", "public/quran")

    # Assert
    assert result.exit_code == 0, result.output
    manifest = parse_manifest_content((tmp_path / "itqan-assets.yaml").read_bytes())
    assert manifest.assets_dir == "public/quran"


@responses.activate
def test_init_command_where_api_key_given_should_not_limit_to_open_access(tmp_path: Path, monkeypatch):
    # Arrange
    monkeypatch.setenv("ITQAN_API_KEY", "key")
    _mock_catalog([SINGLE], query={"page_size": "50"})

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert responses.calls[0].request.headers["X-API-Key"] == "key"


@responses.activate
def test_init_command_where_registry_unreachable_should_write_commented_template(tmp_path: Path):
    # Arrange
    responses.add(responses.GET, f"{REGISTRY}/packages/", body=requests.ConnectionError("offline"))

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert "Could not reach the registry" in result.output
    text = (tmp_path / "itqan-assets.yaml").read_text()
    assert '#   language: "en"' in text
    manifest = parse_manifest_content(text.encode())
    assert manifest.assets == {}
    assert manifest.assets_dir == "assets"


@responses.activate
def test_init_command_where_catalog_is_empty_should_write_commented_template(tmp_path: Path):
    # Arrange
    _mock_catalog([])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert "no installable assets" in result.output
    assert parse_manifest_content((tmp_path / "itqan-assets.yaml").read_bytes()).assets == {}


def test_init_command_where_manifest_exists_should_refuse_and_keep_it(tmp_path: Path):
    # Arrange
    manifest_path = tmp_path / "itqan-assets.yaml"
    manifest_path.write_text("original")

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert manifest_path.read_text() == "original"


@responses.activate
def test_init_command_where_manifest_exists_and_force_should_overwrite(tmp_path: Path):
    # Arrange
    manifest_path = tmp_path / "itqan-assets.yaml"
    manifest_path.write_text("original")
    _mock_catalog([SINGLE])

    # Act
    result = _init(tmp_path, "--force")

    # Assert
    assert result.exit_code == 0, result.output
    assert '  # "mushaf-madinah":' in manifest_path.read_text()


@responses.activate
def test_init_command_where_source_language_code_is_blank_should_describe_it_as_source(tmp_path: Path):
    # Arrange
    _mock_catalog([SINGLE | {"languages": [{"language": "", "is_source": True, "latest_version": "1.3.0"}]}])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert "# Mushaf Madinah — languages: source (1.3.0)" in (tmp_path / "itqan-assets.yaml").read_text()


@responses.activate
def test_init_command_where_next_to_a_flutter_pubspec_should_suggest_install_flutter(tmp_path: Path):
    # Arrange
    _mock_catalog([])
    (tmp_path / "pubspec.yaml").write_text("name: app\nflutter:\n  uses-material-design: true\n")

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert "itqan install --flutter" in result.output


@responses.activate
def test_init_command_where_no_flutter_pubspec_should_suggest_plain_install(tmp_path: Path):
    # Arrange
    _mock_catalog([])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert "--flutter" not in result.output


@responses.activate
def test_init_command_where_no_asset_has_a_second_language_should_still_show_a_language_entry(tmp_path: Path):
    # Arrange
    _mock_catalog([SINGLE])

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    text = (tmp_path / "itqan-assets.yaml").read_text()
    entry = parse_manifest_content(_uncomment(text).encode()).assets["mushaf-madinah"]
    assert (entry.language, entry.version) == ("ar", "^1.0.0")


def _answer_confirm(monkeypatch, answer: bool | None) -> list[str]:
    """Answer every questionary yes/no prompt with `answer`; returns the questions asked."""
    asked: list[str] = []

    def confirm(question, **kwargs):
        asked.append(question)
        return type("Q", (), {"ask": lambda self: answer})()

    monkeypatch.setattr("questionary.confirm", confirm)
    return asked


@responses.activate
def test_init_command_where_in_a_terminal_and_user_says_yes_should_run_browse(tmp_path: Path, monkeypatch):
    # Arrange
    _mock_catalog([SINGLE])
    _mock_catalog([SINGLE], query={"page_size": "50"})  # browse lists the whole catalog
    monkeypatch.setattr(main, main._interactive_terminal.__name__, lambda: True)
    asked = _answer_confirm(monkeypatch, True)
    shown: list[list[str]] = []
    monkeypatch.setattr(
        browse,
        browse.pick_packages.__name__,
        lambda packages, targets, has_api_key: shown.append([p.slug for p in packages]),
    )

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert asked == ["Run `itqan browse` now to pick assets to add?"]
    assert shown == [["mushaf-madinah"]]
    assert (tmp_path / "itqan-assets.yaml").is_file()
    assert "Next, run `itqan browse`" not in result.output


@responses.activate
@pytest.mark.parametrize("answer", [False, None], ids=["no", "ctrl-c"])
def test_init_command_where_in_a_terminal_and_user_declines_should_print_next_steps(
    tmp_path: Path, monkeypatch, answer: bool | None
):
    # Arrange
    _mock_catalog([SINGLE])
    monkeypatch.setattr(main, main._interactive_terminal.__name__, lambda: True)
    asked = _answer_confirm(monkeypatch, answer)

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert len(asked) == 1
    assert "Next, run `itqan browse`" in result.output
    assert len(responses.calls) == 1  # browse never listed the catalog


@responses.activate
def test_init_command_where_not_in_a_terminal_should_not_ask_to_browse(tmp_path: Path, monkeypatch):
    # Arrange
    _mock_catalog([SINGLE])
    monkeypatch.setattr(main, main._interactive_terminal.__name__, lambda: False)
    asked = _answer_confirm(monkeypatch, True)

    # Act
    result = _init(tmp_path)

    # Assert
    assert result.exit_code == 0, result.output
    assert asked == []
    assert "Next, run `itqan browse`" in result.output


def test_cli_help_where_listing_commands_should_not_truncate_their_descriptions():
    # Act
    result = CliRunner().invoke(cli, ["--help"], terminal_width=60)

    # Assert
    assert result.exit_code == 0, result.output
    commands = result.output.split("Commands:")[1]
    assert "..." not in commands
    assert "Same as `itqan install`." in result.output

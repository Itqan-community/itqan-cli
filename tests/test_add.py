"""`itqan add`: add assets to the manifest by name, then install them."""

from pathlib import Path

from click.testing import CliRunner
import pytest
import responses
from responses import matchers

from itqan_cli.add import parse_spec, set_entry_version
from itqan_cli.exceptions import ItqanCliError, ManifestError
from itqan_cli.main import cli
from itqan_cli.manifest import parse_manifest_content

REGISTRY = "https://api.itqan.dev/api"

JALALAYN = {
    "slug": "tafsir-jalalayn",
    "name": "Tafsir al-Jalalayn",
    "category": "tafsir",
    "is_open_access": True,
    "access": "open",
    "languages": [
        {"language": "ar", "is_source": True, "latest_version": "2.4.0"},
        {"language": "en", "is_source": False, "latest_version": "1.3.0"},
    ],
}
GATED = {
    "slug": "gated-tafsir",
    "name": "Gated",
    "category": "tafsir",
    "is_open_access": False,
    "access": "none",
    "access_request_url": "https://cms.itqan.dev/gallery/asset/9",
    "languages": [{"language": "ar", "is_source": True, "latest_version": "1.0.0"}],
}


@pytest.fixture(autouse=True)
def _no_saved_key(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("ITQAN_API_KEY", raising=False)
    monkeypatch.setenv("ITQAN_CONFIG_DIR", str(tmp_path / "config"))


def _mock_catalog(*packages: dict, search: str) -> None:
    responses.add(
        responses.GET,
        f"{REGISTRY}/packages/",
        json={"results": list(packages), "count": len(packages)},
        status=200,
        match=[matchers.query_param_matcher({"page_size": "50", "search": search})],
    )


def _mock_install() -> None:
    responses.add(
        responses.POST,
        f"{REGISTRY}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "tafsir-jalalayn",
                    "asset_version_id": 1,
                    "resolved_version": "2.4.0",
                    "asset_name": "Tafsir al-Jalalayn",
                    "download_url": "https://cdn.itqan.dev/jalalayn.csv",
                }
            ]
        },
        status=200,
    )
    responses.add(responses.GET, "https://cdn.itqan.dev/jalalayn.csv", body=b"surah,ayah,text\n", status=200)


def _add(project: Path, *args: str):
    return CliRunner().invoke(
        cli,
        [
            "add",
            *args,
            "-m",
            str(project / "itqan-assets.yaml"),
            "-l",
            str(project / "itqan-assets.lock"),
            "--registry-url",
            REGISTRY,
        ],
    )


def _manifest(project: Path):
    return parse_manifest_content((project / "itqan-assets.yaml").read_bytes())


@responses.activate
def test_add_command_where_no_manifest_should_create_it_with_caret_latest_and_install(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")
    _mock_install()

    # Act
    result = _add(tmp_path, "tafsir-jalalayn")

    # Assert
    assert result.exit_code == 0, result.output
    entry = _manifest(tmp_path).assets["tafsir-jalalayn"]
    assert (entry.version, entry.language) == ("^2.4.0", None)
    assert (tmp_path / "itqan-assets.lock").is_file()
    assert (tmp_path / "assets" / "tafsir-jalalayn" / "jalalayn.csv").is_file()


@responses.activate
def test_add_command_where_range_given_should_write_it(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn@~2.1", "--no-install")

    # Assert
    assert result.exit_code == 0, result.output
    assert _manifest(tmp_path).assets["tafsir-jalalayn"].version == "~2.1"
    assert not (tmp_path / "itqan-assets.lock").exists()


@responses.activate
def test_add_command_where_language_given_should_add_named_language_entry(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn", "--language", "en", "--no-install")

    # Assert
    assert result.exit_code == 0, result.output
    entry = _manifest(tmp_path).assets["tafsir-jalalayn-en"]
    assert (entry.asset, entry.language, entry.version) == ("tafsir-jalalayn", "en", "^1.3.0")


@responses.activate
def test_add_command_where_asset_already_added_and_range_given_should_update_its_version(tmp_path: Path):
    # Arrange
    (tmp_path / "itqan-assets.yaml").write_text(
        "schema_version: 1\nassets:\n  # my tafsir\n  tafsir-jalalayn:\n    version: '^2.0.0'  # pinned\n"
    )
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn@^2.4.0", "--no-install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "Updated in" in result.output
    text = (tmp_path / "itqan-assets.yaml").read_text()
    assert "# my tafsir" in text
    assert _manifest(tmp_path).assets["tafsir-jalalayn"].version == "^2.4.0"


@responses.activate
def test_add_command_where_asset_already_added_without_range_should_leave_manifest_unchanged(tmp_path: Path):
    # Arrange
    original = 'schema_version: 1\nassets:\n  tafsir-jalalayn:\n    version: "^2.0.0"\n'
    (tmp_path / "itqan-assets.yaml").write_text(original)
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn", "--no-install")

    # Assert
    assert result.exit_code == 0, result.output
    assert "already in" in result.output
    assert (tmp_path / "itqan-assets.yaml").read_text() == original


@responses.activate
def test_add_command_where_asset_unknown_should_fail_and_suggest_browse(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="jalalayn")  # matches by search, but not by slug

    # Act
    result = _add(tmp_path, "jalalayn")

    # Assert
    assert result.exit_code == 1
    assert "No installable asset named 'jalalayn'" in result.output
    assert "itqan browse jalalayn" in result.output
    assert not (tmp_path / "itqan-assets.yaml").exists()


@responses.activate
def test_add_command_where_asset_needs_access_should_fail_without_writing_anything(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")
    _mock_catalog(GATED, search="gated-tafsir")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn", "gated-tafsir")

    # Assert
    assert result.exit_code == 1
    assert "You don't have access to gated-tafsir" in result.output
    assert "https://cms.itqan.dev/gallery/asset/9" in result.output
    assert not (tmp_path / "itqan-assets.yaml").exists()


@responses.activate
def test_add_command_where_language_unavailable_should_fail_listing_languages(tmp_path: Path):
    # Arrange
    _mock_catalog(JALALAYN, search="tafsir-jalalayn")

    # Act
    result = _add(tmp_path, "tafsir-jalalayn", "-L", "fr")

    # Assert
    assert result.exit_code == 1
    assert "not available in fr; it has: ar, en" in result.output


def test_add_command_where_range_invalid_should_fail_before_calling_registry(tmp_path: Path):
    # Act
    result = _add(tmp_path, "tafsir-jalalayn@banana")

    # Assert
    assert result.exit_code == 1
    assert "Invalid version range" in result.output


def test_parse_spec_where_range_given_should_split_it():
    assert parse_spec("tafsir-jalalayn@^2.0.0") == ("tafsir-jalalayn", "^2.0.0")
    assert parse_spec("tafsir-jalalayn") == ("tafsir-jalalayn", None)


def test_parse_spec_where_name_missing_should_raise():
    with pytest.raises(ItqanCliError):
        parse_spec("@^1.0.0")


def test_set_entry_version_where_entry_has_other_fields_should_only_change_version():
    # Arrange
    content = (
        "schema_version: 1\nassets:\n"
        '  "a-en":\n    asset: "a"\n    language: "en"\n    version: "^1.0.0"\n'
        '  "b":\n    version: "^1.0.0"\n'
    )

    # Act
    updated = set_entry_version(content, "a-en", "~1.2")

    # Assert
    manifest = parse_manifest_content(updated.encode())
    assert manifest.assets["a-en"].version == "~1.2"
    assert manifest.assets["a-en"].language == "en"
    assert manifest.assets["b"].version == "^1.0.0"
    assert updated.count("~1.2") == 1


def test_set_entry_version_where_entry_missing_should_raise():
    with pytest.raises(ManifestError):
        set_entry_version('schema_version: 1\nassets:\n  "b":\n    version: "^1.0.0"\n', "a", "^2.0.0")

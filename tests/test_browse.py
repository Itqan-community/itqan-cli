"""`itqan browse`: list the catalog, pick assets and add them to the manifest."""

import json
from pathlib import Path

from click.testing import CliRunner
import pytest
import responses
from responses import matchers

from itqan_cli import browse
from itqan_cli.client import CatalogLanguage, CatalogPackage, RegistryClient
from itqan_cli.exceptions import ManifestError, RegistryApiError
from itqan_cli.init_template import render_fallback, render_from_catalog
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
GATED = {
    "slug": "font-hafs",
    "name": "Hafs Font",
    "category": "font",
    "is_open_access": False,
    "publisher_name": None,
    "languages": [{"language": "ar", "is_source": True, "latest_version": "3.0.0"}],
}


def _package(raw: dict) -> CatalogPackage:
    return CatalogPackage(
        slug=raw["slug"],
        name=raw["name"],
        category=raw["category"],
        is_open_access=raw["is_open_access"],
        publisher_name=raw["publisher_name"],
        languages=tuple(CatalogLanguage(**lang) for lang in raw["languages"]),
    )


def _mock_catalog(results: list[dict], *, query: dict | None = None, count: int | None = None) -> None:
    responses.add(
        responses.GET,
        f"{REGISTRY}/packages/",
        json={"results": results, "count": len(results) if count is None else count},
        status=200,
        match=[matchers.query_param_matcher(query or {"page_size": "50"})],
    )


def _browse(project: Path, *extra: str):
    return CliRunner().invoke(
        cli, ["browse", "-m", str(project / "itqan-assets.yaml"), "--registry-url", REGISTRY, *extra]
    )


# --- client -------------------------------------------------------------------


@responses.activate
def test_list_all_packages_where_catalog_has_two_pages_should_return_both():
    # Arrange
    _mock_catalog([SINGLE], query={"page_size": "1"}, count=2)
    _mock_catalog([MULTILINGUAL], query={"page_size": "1", "page": "2"}, count=2)

    # Act
    packages = RegistryClient(base_url=REGISTRY).list_all_packages(page_size=1)

    # Assert
    assert [package.slug for package in packages] == ["mushaf-madinah", "tafsir-jalalayn"]


@responses.activate
def test_list_all_packages_where_search_and_category_given_should_send_them():
    # Arrange
    _mock_catalog([SINGLE], query={"page_size": "50", "search": "madinah", "category": "mushaf"})

    # Act
    packages = RegistryClient(base_url=REGISTRY).list_all_packages(search="madinah", category="mushaf")

    # Assert
    assert [package.slug for package in packages] == ["mushaf-madinah"]


@responses.activate
def test_list_all_packages_where_registry_rejects_filter_should_report_reason():
    # Arrange
    responses.add(
        responses.GET,
        f"{REGISTRY}/packages/",
        json={"error_name": "validation_error", "message": "Invalid Input", "extra": [{"msg": "Input should be 'mushaf'"}]},
        status=400,
    )

    # Act / Assert
    with pytest.raises(RegistryApiError, match="Input should be 'mushaf'"):
        RegistryClient(base_url=REGISTRY).list_all_packages(category="nope")


# --- planning entries -----------------------------------------------------------


def test_plan_entries_where_language_is_not_source_should_name_entry_after_language():
    # Arrange
    package = _package(MULTILINGUAL)

    # Act
    entries, warnings = browse.plan_entries([(package, package.languages[1])], manifest=None)

    # Assert
    assert [entry.name for entry in entries] == ["tafsir-jalalayn-en"]
    assert warnings == []


def test_plan_entries_where_asset_already_declared_should_skip_with_warning():
    # Arrange
    package = _package(SINGLE)
    manifest = parse_manifest_content(b'schema_version: 1\nassets:\n  mushaf-madinah:\n    version: "^1.0.0"\n')

    # Act
    entries, warnings = browse.plan_entries([(package, package.languages[0])], manifest)

    # Assert
    assert entries == []
    assert "already in the manifest" in warnings[0]


def test_unavailable_reason_where_gated_without_api_key_should_need_key():
    # Arrange
    package = _package(GATED)

    # Act
    without_key = browse.unavailable_reason(package, set(), has_api_key=False)
    with_key = browse.unavailable_reason(package, set(), has_api_key=True)

    # Assert
    assert without_key == "needs an API key"
    assert with_key is None


# --- editing the manifest -------------------------------------------------------


def _entries(*picks: tuple[dict, int]) -> list[browse.NewEntry]:
    entries, _ = browse.plan_entries([(_package(raw), _package(raw).languages[i]) for raw, i in picks], None)
    return entries


def test_add_entries_where_manifest_from_init_should_keep_comments_and_add_entry():
    # Arrange
    content = render_from_catalog([_package(SINGLE)], "assets")

    # Act
    updated = browse.add_entries(content, _entries((MULTILINGUAL, 1)))

    # Assert
    assert updated.startswith(content.rstrip("\n"))  # nothing before the new entry changed
    assert "# Mushaf Madinah — languages" in updated
    english = parse_manifest_content(updated.encode()).assets["tafsir-jalalayn-en"]
    assert (english.asset, english.language, english.version) == ("tafsir-jalalayn", "en", "^1.3.0")


def test_add_entries_where_assets_only_has_comments_should_add_under_it():
    # Arrange
    content = render_fallback("assets", reason="Offline,")

    # Act
    updated = browse.add_entries(content, _entries((SINGLE, 0)))

    # Assert
    assert list(parse_manifest_content(updated.encode()).assets) == ["mushaf-madinah"]


def test_add_entries_where_assets_is_not_last_key_and_uses_four_spaces_should_match_indent():
    # Arrange
    content = (
        "schema_version: 1\n"
        "assets:\n"
        "    mushaf-madinah:\n"
        '        version: "^1.0.0"\n'
        "# where files go\n"
        "assets_dir: public\n"
    )

    # Act
    updated = browse.add_entries(content, _entries((MULTILINGUAL, 0)))

    # Assert
    manifest = parse_manifest_content(updated.encode())
    assert list(manifest.assets) == ["mushaf-madinah", "tafsir-jalalayn"]
    assert manifest.assets_dir == "public"
    assert '    "tafsir-jalalayn":\n        version: "^2.4.0"' in updated


def test_add_entries_where_assets_is_flow_mapping_should_raise():
    # Arrange
    content = "schema_version: 1\nassets: {}\n"

    # Act / Assert
    with pytest.raises(ManifestError):
        browse.add_entries(content, _entries((SINGLE, 0)))


# --- the command ----------------------------------------------------------------


@responses.activate
def test_browse_command_where_not_interactive_should_print_table_marking_declared(tmp_path: Path):
    # Arrange
    (tmp_path / "itqan-assets.yaml").write_text('schema_version: 1\nassets:\n  mushaf-madinah:\n    version: "^1.0.0"\n')
    _mock_catalog([SINGLE, GATED])

    # Act
    result = _browse(tmp_path, "--no-interactive")

    # Assert
    assert result.exit_code == 0, result.output
    assert "* mushaf-madinah" in result.output
    assert "font-hafs" in result.output and "api-key" in result.output


@responses.activate
def test_browse_command_where_json_given_should_print_catalog_as_json(tmp_path: Path):
    # Arrange
    _mock_catalog([SINGLE], query={"page_size": "50", "search": "madinah"})

    # Act
    result = _browse(tmp_path, "madinah", "--json")

    # Assert
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body[0]["slug"] == "mushaf-madinah"
    assert body[0]["languages"][0]["in_manifest"] is False


@responses.activate
def test_browse_command_where_assets_picked_should_create_manifest_with_them(tmp_path: Path, monkeypatch):
    # Arrange
    _mock_catalog([SINGLE, MULTILINGUAL])
    monkeypatch.setattr(browse, browse.pick_packages.__name__, lambda packages, targets, has_api_key: packages)
    monkeypatch.setattr(
        browse, browse.pick_languages.__name__, lambda package, targets: list(package.languages)
    )
    monkeypatch.setattr("questionary.confirm", lambda *args, **kwargs: type("Q", (), {"ask": lambda self: False})())

    # Act
    result = _browse(tmp_path, "--interactive")

    # Assert
    assert result.exit_code == 0, result.output
    manifest = parse_manifest_content((tmp_path / "itqan-assets.yaml").read_bytes())
    assert list(manifest.assets) == ["mushaf-madinah", "tafsir-jalalayn", "tafsir-jalalayn-en"]
    assert "Added 3 asset(s)" in result.output
    assert "Run `itqan install` when you're ready" in result.output


@responses.activate
def test_browse_command_where_picker_cancelled_should_not_write_manifest(tmp_path: Path, monkeypatch):
    # Arrange
    _mock_catalog([SINGLE])
    monkeypatch.setattr(browse, browse.pick_packages.__name__, lambda packages, targets, has_api_key: None)

    # Act
    result = _browse(tmp_path, "--interactive")

    # Assert
    assert result.exit_code == 0, result.output
    assert "Nothing added." in result.output
    assert not (tmp_path / "itqan-assets.yaml").exists()


@responses.activate
def test_browse_command_where_no_match_should_say_so(tmp_path: Path):
    # Arrange
    _mock_catalog([], query={"page_size": "50", "search": "zzz"})

    # Act
    result = _browse(tmp_path, "zzz", "--no-interactive")

    # Assert
    assert result.exit_code == 0, result.output
    assert "No assets match." in result.output


def test_choice_titles_where_name_is_long_should_fit_width_with_room_for_reason():
    # Arrange
    long_name = dict(GATED, name="A very long asset name that would never fit in a narrow terminal window")
    packages = [_package(SINGLE), _package(long_name)]
    reasons = [None, "needs an API key"]

    # Act
    titles = browse.choice_titles(packages, reasons, max_width=80)

    # Assert
    assert titles[0].endswith("Mushaf Madinah")
    assert titles[1].endswith("…")
    assert len(titles[1]) + len(" (needs an API key)") + 5 <= 80
    assert titles[0].index("mushaf ") == titles[1].index("font ")  # columns line up


def test_choice_description_where_gated_should_name_publisher_and_access():
    # Arrange
    package = _package(dict(GATED, publisher_name="King Fahd Complex"))

    # Act
    description = browse.choice_description(package)

    # Assert
    assert description == "Hafs Font · King Fahd Complex · needs an API key"


def _run_picker(keys: str) -> list[CatalogPackage] | None:
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        return browse.pick_packages(
            [_package(SINGLE), _package(MULTILINGUAL), _package(GATED)],
            set(),
            has_api_key=False,
            input=pipe,
            output=DummyOutput(),
        )


def test_pick_packages_where_enter_pressed_with_nothing_selected_should_pick_highlighted():
    # Arrange
    down_arrow = "\x1b[B"

    # Act
    picked = _run_picker(down_arrow + "\r")

    # Assert
    assert [package.slug for package in picked] == ["tafsir-jalalayn"]


def test_pick_packages_where_rows_selected_with_space_should_return_only_those():
    # Arrange
    down_arrow = "\x1b[B"

    # Act
    picked = _run_picker(" " + down_arrow + " " + "\r")

    # Assert
    assert [package.slug for package in picked] == ["mushaf-madinah", "tafsir-jalalayn"]


def test_pick_packages_where_search_matches_nothing_should_pick_nothing():
    # Arrange / Act
    picked = _run_picker("zzz\r")

    # Assert
    assert picked == []


def test_pick_packages_where_search_given_should_pick_first_match():
    # Arrange / Act
    picked = _run_picker("jalal\r")

    # Assert
    assert [package.slug for package in picked] == ["tafsir-jalalayn"]

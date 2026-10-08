"""Access-aware `browse`, `install` and `init`: gated assets are listed with
where to request access, and only installable ones can be picked."""

import json
from pathlib import Path

from click.testing import CliRunner
import pytest
import responses
from responses import matchers

from itqan_cli import browse, credentials
from itqan_cli.client import CatalogLanguage, CatalogPackage
from itqan_cli.main import cli

REGISTRY = "https://registry.example"
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


def _gated(slug: str, access: str) -> dict:
    return {
        "slug": slug,
        "name": slug.title(),
        "category": "tafsir",
        "is_open_access": False,
        "access": access,
        "access_request_url": f"https://cms.example/gallery/asset/{slug}",
        "publisher_name": None,
        "languages": [{"language": "ar", "is_source": True, "latest_version": "2.0.0"}],
    }


def _package(raw: dict) -> CatalogPackage:
    return CatalogPackage(
        slug=raw["slug"],
        name=raw["name"],
        category=raw["category"],
        is_open_access=raw["is_open_access"],
        publisher_name=raw["publisher_name"],
        access=raw.get("access"),
        access_request_url=raw.get("access_request_url"),
        languages=tuple(CatalogLanguage(**lang) for lang in raw["languages"]),
    )


def _mock_catalog(results: list[dict], **kwargs) -> None:
    responses.add(
        responses.GET, f"{REGISTRY}/packages/", json={"results": results, "count": len(results)}, status=200, **kwargs
    )


def _run(*args: str, input: str | None = None):
    return CliRunner().invoke(cli, list(args), input=input)


# --- access in browse -----------------------------------------------------------


@pytest.mark.parametrize(
    ("access", "has_key", "reason"),
    [
        ("open", False, None),
        ("granted", True, None),
        ("pending", True, "access pending"),
        ("rejected", True, "access rejected"),
        ("none", False, "request access"),
        ("none", True, "request access"),
    ],
)
def test_unavailable_reason_where_access_given_should_match(access, has_key, reason):
    # Arrange
    package = _package(OPEN if access == "open" else _gated("tafsir-x", access))

    # Act / Assert
    assert browse.unavailable_reason(package, set(), has_api_key=has_key) == reason


def test_unavailable_reason_where_registry_predates_access_should_fall_back_to_key():
    # Arrange
    package = _package(dict(_gated("tafsir-x", "none"), access=None, access_request_url=None))

    # Act / Assert
    assert browse.unavailable_reason(package, set(), has_api_key=False) == "needs an API key"
    assert browse.unavailable_reason(package, set(), has_api_key=True) is None


def test_choice_description_where_access_needed_should_link_request_page_and_login():
    # Arrange
    package = _package(_gated("tafsir-x", "none"))

    # Act
    description = browse.choice_description(package, has_api_key=False)

    # Assert
    assert "request at https://cms.example/gallery/asset/tafsir-x" in description
    assert "itqan login" in description


@responses.activate
def test_browse_command_where_not_interactive_should_list_request_pages(tmp_path: Path):
    # Arrange
    _mock_catalog([OPEN, _gated("tafsir-pending", "pending"), _gated("tafsir-granted", "granted")])

    # Act
    result = _run("browse", "-m", str(tmp_path / "m.yaml"), "--registry-url", REGISTRY, "--no-interactive")

    # Assert
    assert result.exit_code == 0, result.output
    assert "Request access on each asset's page:" in result.output
    assert "tafsir-pending  https://cms.example/gallery/asset/tafsir-pending  (access pending)" in result.output
    assert "gallery/asset/tafsir-granted" not in result.output
    assert "Run `itqan login`" in result.output


@responses.activate
def test_browse_command_where_json_should_include_access(tmp_path: Path):
    # Arrange
    _mock_catalog([_gated("tafsir-x", "rejected")])

    # Act
    result = _run("browse", "-m", str(tmp_path / "m.yaml"), "--registry-url", REGISTRY, "--json")

    # Assert
    item = json.loads(result.output)[0]
    assert (item["access"], item["access_request_url"]) == ("rejected", "https://cms.example/gallery/asset/tafsir-x")


# --- install / init -------------------------------------------------------------


@responses.activate
def test_install_command_where_access_denied_should_name_asset_and_request_page(tmp_path: Path):
    # Arrange
    manifest = tmp_path / "itqan-assets.yaml"
    manifest.write_text('schema_version: 1\nassets:\n  tafsir-x:\n    version: "^2.0.0"\n')
    credentials.save_api_key(REGISTRY, KEY)
    responses.add(
        responses.POST,
        f"{REGISTRY}/packages/resolve/manifest/",
        json={"error_name": "access_denied", "message": "You don't have an approved access request for this asset."},
        status=403,
    )
    _mock_catalog([_gated("tafsir-x", "pending")])

    # Act
    result = _run("install", "-m", str(manifest), "-l", str(tmp_path / "itqan-assets.lock"), "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 1
    assert "Request access on each asset's page:" in result.output
    assert "tafsir-x  https://cms.example/gallery/asset/tafsir-x  (access pending)" in result.output
    assert "itqan login" not in result.output  # a key is already in use


@responses.activate
def test_init_command_where_key_given_should_skip_assets_without_access(tmp_path: Path):
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_catalog(
        [_gated("tafsir-none", "none"), _gated("tafsir-granted", "granted")],
        match=[matchers.query_param_matcher({"page_size": "50"})],
    )

    # Act
    result = _run("init", "-m", str(tmp_path / "itqan-assets.yaml"), "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 0, result.output
    text = (tmp_path / "itqan-assets.yaml").read_text()
    assert '"tafsir-granted"' in text
    assert "tafsir-none" not in text

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


# --- request-access -------------------------------------------------------------


def _mock_request_access(slug: str = "tafsir-x", *, status_code: int = 200, **body) -> None:
    payload = (dict(body, slug=slug) if body else None) or {
        "slug": slug,
        "request_id": 7,
        "status": "pending",
        "created": True,
        "access_request_url": f"https://cms.example/gallery/asset/{slug}",
    }
    responses.add(responses.POST, f"{REGISTRY}/packages/{slug}/request-access/", json=payload, status=status_code)


@responses.activate
def test_request_access_command_where_new_should_send_use_and_report_pending():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_request_access()

    # Act
    result = _run("request-access", "tafsir-x", "-u", "commercial", "-p", "My app", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 0, result.output
    assert "Requested access to tafsir-x" in result.output
    assert "https://cms.example/gallery/asset/tafsir-x" in result.output
    sent = responses.calls[0].request
    assert json.loads(sent.body) == {"intended_use": "commercial", "purpose": "My app"}
    assert sent.headers["X-API-Key"] == KEY


@responses.activate
def test_request_access_command_where_already_pending_should_say_so():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_request_access(slug="tafsir-x", request_id=7, status="pending", created=False, access_request_url=None)

    # Act
    result = _run("request-access", "tafsir-x", "-u", "non-commercial", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 0, result.output
    assert "already asked for access to tafsir-x; it is still pending" in result.output
    assert json.loads(responses.calls[0].request.body) == {"intended_use": "non-commercial"}


@responses.activate
def test_request_access_command_where_auto_approved_should_point_to_add():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_request_access(slug="tafsir-x", request_id=7, status="approved", created=True, access_request_url=None)

    # Act
    result = _run("request-access", "tafsir-x", "-u", "commercial", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 0, result.output
    assert "approved" in result.output
    assert "itqan add tafsir-x" in result.output


def test_request_access_command_where_no_key_should_ask_to_log_in():
    # Act
    result = _run("request-access", "tafsir-x", "-u", "commercial", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 1
    assert "itqan login" in result.output


@responses.activate
def test_request_access_command_where_use_missing_and_not_interactive_should_fail_without_calling():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)

    # Act
    result = _run("request-access", "tafsir-x", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 1
    assert "--intended-use" in result.output
    assert len(responses.calls) == 0


@responses.activate
def test_request_access_command_where_asset_open_should_say_no_request_needed():
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_request_access(
        "mushaf-madinah",
        status_code=409,
        error_name="access_not_required",
        message="mushaf-madinah is open access; no request is needed.",
    )

    # Act
    result = _run("request-access", "mushaf-madinah", "-u", "commercial", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 0, result.output
    assert "open access" in result.output
    assert "itqan add mushaf-madinah" in result.output


@responses.activate
@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "did not accept the API key"), (404, "No asset named 'tafsir-x'"), (500, "status 500")],
)
def test_request_access_command_where_registry_refuses_should_explain(status, expected):
    # Arrange
    credentials.save_api_key(REGISTRY, KEY)
    _mock_request_access(status_code=status, error_name="x", message="nope")

    # Act
    result = _run("request-access", "tafsir-x", "-u", "commercial", "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 1
    assert expected in result.output


@pytest.mark.parametrize(
    ("access", "has_key", "hint"),
    [("none", True, "`itqan request-access tafsir-x`"), ("rejected", False, "(after `itqan login`)")],
)
def test_access_footer_where_request_possible_should_hint_the_command(access, has_key, hint):
    # Arrange
    package = _package(_gated("tafsir-x", access))

    # Act
    footer = "\n".join(browse.access_footer([package], has_api_key=has_key))

    # Assert
    assert hint in footer


def test_access_footer_where_request_already_pending_should_not_hint_the_command():
    # Act
    footer = "\n".join(browse.access_footer([_package(_gated("tafsir-x", "pending"))], has_api_key=True))

    # Assert
    assert "request-access" not in footer


@responses.activate
def test_install_command_where_access_not_requested_should_hint_request_access(tmp_path: Path):
    # Arrange
    manifest = tmp_path / "itqan-assets.yaml"
    manifest.write_text('schema_version: 1\nassets:\n  tafsir-x:\n    version: "^2.0.0"\n')
    credentials.save_api_key(REGISTRY, KEY)
    responses.add(
        responses.POST,
        f"{REGISTRY}/packages/resolve/manifest/",
        json={"error_name": "access_denied", "message": "No approved access request."},
        status=403,
    )
    _mock_catalog([_gated("tafsir-x", "none")])

    # Act
    result = _run("install", "-m", str(manifest), "-l", str(tmp_path / "itqan-assets.lock"), "--registry-url", REGISTRY)

    # Assert
    assert result.exit_code == 1
    assert "itqan request-access tafsir-x" in result.output

"""Tests for Package Registry HTTP Client."""

from importlib.metadata import version

from click.testing import CliRunner
import pytest
import responses

from itqan_cli.client import RegistryClient
from itqan_cli.exceptions import RegistryApiError
from itqan_cli.main import cli, install_command


@responses.activate
def test_resolve_manifest_where_valid_constraints_should_return_resolved_assets():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "quran-uthmani-hafs",
                    "asset_version_id": 12,
                    "resolved_version": "2.4.1",
                    "asset_name": "Quran Hafs",
                    "download_url": "https://cdn.itqan.dev/assets/quran.zip",
                    "publisher_id": 1,
                    "publisher_name": "KAFD",
                }
            ]
        },
        status=200,
    )

    client = RegistryClient(base_url=base_url, api_key="secret-test-key")
    results = client.resolve_manifest({"quran-uthmani-hafs": "^2.1.0"})

    assert len(results) == 1
    assert results[0].slug == "quran-uthmani-hafs"
    assert results[0].resolved_version == "2.4.1"
    assert results[0].download_url == "https://cdn.itqan.dev/assets/quran.zip"


@responses.activate
def test_resolve_manifest_where_api_key_missing_should_raise_registry_api_error_401():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={"error_name": "authentication_required", "message": "API key required"},
        status=401,
    )

    client = RegistryClient(base_url=base_url)
    with pytest.raises(RegistryApiError) as exc_info:
        client.resolve_manifest({"quran": "1.0.0"})

    assert exc_info.value.status_code == 401
    assert "Authentication required" in exc_info.value.message


@responses.activate
def test_resolve_manifest_where_asset_access_denied_should_raise_registry_api_error_403():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={"error_name": "access_denied", "message": "No active license"},
        status=403,
    )

    client = RegistryClient(base_url=base_url, api_key="valid-key")
    with pytest.raises(RegistryApiError) as exc_info:
        client.resolve_manifest({"restricted-asset": "1.0.0"})

    assert exc_info.value.status_code == 403
    assert "Access denied" in exc_info.value.message


@responses.activate
def test_resolve_manifest_where_no_version_satisfies_constraint_should_raise_registry_api_error_422():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={"error_name": "unsatisfiable_version_constraint", "message": "No matching version"},
        status=422,
    )

    client = RegistryClient(base_url=base_url)
    with pytest.raises(RegistryApiError) as exc_info:
        client.resolve_manifest({"quran": "^99.0.0"})

    assert exc_info.value.status_code == 422
    assert "Cannot satisfy version constraints" in exc_info.value.message


def test_registry_client_where_no_base_url_given_should_default_to_production():
    # Arrange / Act
    client = RegistryClient()

    # Assert
    assert client.base_url == "https://api.cms.itqan.dev"


def test_install_command_where_no_registry_url_given_should_default_to_production():
    # Arrange / Act
    option = next(param for param in install_command.params if param.name == "registry_url")

    # Assert
    assert option.default == "https://api.cms.itqan.dev"


def test_cli_where_version_flag_given_should_print_package_version():
    # Arrange / Act
    result = CliRunner().invoke(cli, ["--version"])

    # Assert
    assert result.exit_code == 0, result.output
    assert result.output.strip() == f"itqan, version {version('itqan-cli')}"


@responses.activate
def test_resolve_manifest_where_called_should_send_installed_version_in_user_agent():
    # Arrange
    responses.add(responses.POST, "https://api.cms.itqan.dev/packages/resolve/manifest/", json={"results": []})

    # Act
    RegistryClient().resolve_manifest({})

    # Assert
    assert responses.calls[0].request.headers["User-Agent"] == f"itqan-cli/{version('itqan-cli')}"


@responses.activate
def test_resolve_manifest_where_version_withdrawn_should_carry_withdrawal():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "hafs-tafsir",
                    "asset_version_id": 7,
                    "resolved_version": "1.3.0",
                    "asset_name": "Hafs Tafsir",
                    "download_url": "https://cdn.itqan.dev/assets/tafsir.csv",
                    "withdrawn": True,
                    "withdrawal_reason": "Errors in Surah 2",
                }
            ]
        },
        status=200,
    )

    client = RegistryClient(base_url=base_url)
    results = client.resolve_manifest({"hafs-tafsir": "1.3.0"})

    assert results[0].withdrawn is True
    assert results[0].withdrawal_reason == "Errors in Surah 2"


@responses.activate
def test_resolve_manifest_where_registry_omits_withdrawn_should_default_to_not_withdrawn():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "hafs-tafsir",
                    "asset_version_id": 7,
                    "resolved_version": "1.3.0",
                    "asset_name": "Hafs Tafsir",
                    "download_url": None,
                }
            ]
        },
        status=200,
    )

    client = RegistryClient(base_url=base_url)
    results = client.resolve_manifest({"hafs-tafsir": "1.3.0"})

    assert results[0].withdrawn is False
    assert results[0].withdrawal_reason is None


@responses.activate
def test_resolve_manifest_where_version_removed_should_raise_registry_api_error_410():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={"error_name": "version_removed", "message": "Version 1.0.0 of m1 was removed by Itqan. Licence revoked."},
        status=410,
    )

    client = RegistryClient(base_url=base_url)
    with pytest.raises(RegistryApiError) as exc_info:
        client.resolve_manifest({"m1": "1.0.0"})

    assert exc_info.value.status_code == 410
    assert exc_info.value.error_name == "version_removed"
    assert "Licence revoked." in exc_info.value.message
    assert "itqan install --force" in exc_info.value.message


QA_STRUCTURE = {
    "template": "ayah",
    "header": ["surah", "ayah", "question", "answer"],
    "columns": [
        {"key": "question", "label_en": "Question", "label_ar": "السؤال"},
        {"key": "answer", "label_en": "Answer", "label_ar": "الجواب"},
    ],
}


@responses.activate
def test_list_packages_where_language_has_structure_should_parse_it():
    from itqan_cli.columns_comment import PackageColumn, PackageStructure

    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.GET,
        f"{base_url}/packages/",
        json={
            "results": [
                {
                    "slug": "qa",
                    "name": "QA",
                    "category": "tafsir",
                    "is_open_access": True,
                    "languages": [
                        {"language": "ar", "is_source": True, "latest_version": "1.0.0", "structure": QA_STRUCTURE},
                        {"language": "en", "is_source": False, "latest_version": "1.0.0"},
                    ],
                }
            ],
            "count": 1,
        },
        status=200,
    )

    packages = RegistryClient(base_url=base_url).list_packages()

    assert packages[0].languages[0].structure == PackageStructure(
        template="ayah",
        header=("surah", "ayah", "question", "answer"),
        columns=(PackageColumn("question", "Question", "السؤال"), PackageColumn("answer", "Answer", "الجواب")),
    )
    assert packages[0].languages[1].structure is None


@responses.activate
def test_resolve_manifest_where_result_has_structure_should_parse_it():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.POST,
        f"{base_url}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "qa",
                    "asset_version_id": 1,
                    "resolved_version": "1.0.0",
                    "asset_name": "QA",
                    "download_url": "https://cdn.itqan.dev/qa.csv",
                    "structure": QA_STRUCTURE,
                }
            ]
        },
        status=200,
    )

    results = RegistryClient(base_url=base_url).resolve_manifest({"qa": "^1.0.0"})

    assert results[0].structure.header == ("surah", "ayah", "question", "answer")


@responses.activate
def test_list_packages_where_structure_is_malformed_should_raise_registry_api_error():
    base_url = "https://api.itqan.dev/api"
    responses.add(
        responses.GET,
        f"{base_url}/packages/",
        json={
            "results": [
                {
                    "slug": "qa",
                    "name": "QA",
                    "category": "tafsir",
                    "is_open_access": True,
                    "languages": [
                        {"language": "ar", "is_source": True, "latest_version": "1.0.0", "structure": {"template": 1}}
                    ],
                }
            ],
            "count": 1,
        },
        status=200,
    )

    with pytest.raises(RegistryApiError):
        RegistryClient(base_url=base_url).list_packages()

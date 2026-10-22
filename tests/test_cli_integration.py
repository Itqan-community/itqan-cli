"""End-to-end integration tests for the Itqan CLI commands (install and sync)."""

from pathlib import Path

from click.testing import CliRunner
import pytest
import responses

from itqan_cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


@responses.activate
def test_install_command_where_valid_manifest_and_api_responds_should_write_lockfile_and_materialize_assets(
    runner: CliRunner, tmp_path: Path
):
    manifest_path = tmp_path / "itqan-assets.yaml"
    lockfile_path = tmp_path / "itqan-assets.lock"
    assets_dir = tmp_path / "assets"
    registry_url = "https://api.itqan.dev/api"

    manifest_path.write_bytes(b"""schema_version: 1

assets:
  quran-uthmani-hafs:
    version: "^2.1.0"
""")

    # Mock Registry API
    responses.add(
        responses.POST,
        f"{registry_url}/packages/resolve/manifest/",
        json={
            "results": [
                {
                    "slug": "quran-uthmani-hafs",
                    "asset_version_id": 10,
                    "resolved_version": "2.4.1",
                    "asset_name": "Quran Hafs",
                    "download_url": "https://cdn.itqan.dev/assets/quran.pdf",
                }
            ]
        },
        status=200,
    )

    # Mock File Download
    responses.add(
        responses.GET,
        "https://cdn.itqan.dev/assets/quran.pdf",
        body=b"%PDF-1.4 dummy pdf bytes",
        status=200,
    )

    # 1. Run itqan install
    result = runner.invoke(
        cli,
        [
            "install",
            "--manifest",
            str(manifest_path),
            "--lockfile",
            str(lockfile_path),
            "--assets-dir",
            str(assets_dir),
            "--registry-url",
            registry_url,
            "--api-key",
            "test-api-key",
        ],
    )

    assert result.exit_code == 0
    assert "Success!" in result.output
    assert "Updated lockfile" in result.output

    # Verify lockfile written
    assert lockfile_path.is_file()
    lock_content = lockfile_path.read_text(encoding="utf-8")
    assert '"quran-uthmani-hafs":' in lock_content
    assert 'version: "2.4.1"' in lock_content

    # Verify asset file written
    target_asset = assets_dir / "quran-uthmani-hafs" / "quran.pdf"
    assert target_asset.is_file()
    assert target_asset.read_bytes() == b"%PDF-1.4 dummy pdf bytes"

    # 2. Run itqan sync (alias) again -> verify FRESH state & idempotency
    result_sync = runner.invoke(
        cli,
        [
            "sync",
            "--manifest",
            str(manifest_path),
            "--lockfile",
            str(lockfile_path),
            "--assets-dir",
            str(assets_dir),
            "--registry-url",
            registry_url,
            "--api-key",
            "test-api-key",
        ],
    )

    assert result_sync.exit_code == 0
    assert "Lockfile is FRESH" in result_sync.output
    assert "cached (up-to-date)" in result_sync.output


def test_install_command_where_manifest_file_absent_should_exit_with_code_1_and_clear_error(
    runner: CliRunner, tmp_path: Path
):
    non_existent = tmp_path / "itqan-assets.yaml"
    result = runner.invoke(cli, ["install", "--manifest", str(non_existent)])
    assert result.exit_code == 1
    assert "No manifest found" in result.output


@responses.activate
def test_install_command_where_registry_returns_401_should_exit_with_code_1_and_auth_error_message(
    runner: CliRunner, tmp_path: Path
):
    manifest_path = tmp_path / "itqan-assets.yaml"
    manifest_path.write_bytes(b"""schema_version: 1
assets:
  quran-uthmani-hafs:
    version: "^2.1.0"
""")
    registry_url = "https://api.itqan.dev/api"

    responses.add(
        responses.POST,
        f"{registry_url}/packages/resolve/manifest/",
        json={"error_name": "authentication_required", "message": "API key required"},
        status=401,
    )

    result = runner.invoke(
        cli,
        [
            "install",
            "--manifest",
            str(manifest_path),
            "--registry-url",
            registry_url,
        ],
    )
    assert result.exit_code == 1
    assert "Authentication required" in result.output


@responses.activate
def test_install_command_where_locked_version_withdrawn_should_install_it_and_warn(runner: CliRunner, tmp_path: Path):
    manifest_path = tmp_path / "itqan-assets.yaml"
    lockfile_path = tmp_path / "itqan-assets.lock"
    assets_dir = tmp_path / "assets"
    registry_url = "https://api.itqan.dev/api"
    manifest_path.write_bytes(b"""schema_version: 1

assets:
  hafs-tafsir:
    version: "^1.0.0"
""")
    responses.add(
        responses.POST,
        f"{registry_url}/packages/resolve/manifest/",
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
    responses.add(responses.GET, "https://cdn.itqan.dev/assets/tafsir.csv", body=b"surah,ayah,text\n", status=200)

    result = runner.invoke(
        cli,
        [
            "install",
            "--manifest",
            str(manifest_path),
            "--lockfile",
            str(lockfile_path),
            "--assets-dir",
            str(assets_dir),
            "--registry-url",
            registry_url,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "hafs-tafsir 1.3.0 was withdrawn by its publisher: Errors in Surah 2" in result.output
    assert "itqan install --force" in result.output
    assert (assets_dir / "hafs-tafsir" / "tafsir.csv").is_file()


@responses.activate
def test_install_command_where_manifest_has_no_assets_should_suggest_browse(runner: CliRunner, tmp_path: Path):
    # Arrange
    manifest_path = tmp_path / "itqan-assets.yaml"
    manifest_path.write_text('schema_version: 1\n\nassets:\n  # "mushaf-madinah":\n  #   version: "^1.0.0"\n')
    registry_url = "https://api.itqan.dev/api"
    responses.add(responses.POST, f"{registry_url}/packages/resolve/manifest/", json={"results": []}, status=200)

    # Act
    result = runner.invoke(
        cli,
        [
            "install",
            "-m",
            str(manifest_path),
            "-l",
            str(tmp_path / "itqan-assets.lock"),
            "--registry-url",
            registry_url,
        ],
    )

    # Assert
    assert result.exit_code == 0, result.output
    assert "has no assets yet: run `itqan browse`" in result.output


QA_MANIFEST = b"""schema_version: 1

assets:
  # itqan:columns CSV, one row per ayah: surah, ayah, question, answer
  qa:
    version: "^1.0.0"
"""
QA_STRUCTURE = {
    "template": "ayah",
    "header": ["surah", "ayah", "question", "answer", "extra"],
    "columns": [
        {"key": "question", "label_en": "Question", "label_ar": ""},
        {"key": "answer", "label_en": "", "label_ar": ""},
        {"key": "extra", "label_en": "", "label_ar": ""},
    ],
}


def _mock_qa_resolve(registry_url: str, *, structure: dict | None, download_status: int = 200) -> None:
    result = {
        "slug": "qa",
        "asset_version_id": 7,
        "resolved_version": "1.1.0",
        "asset_name": "QA",
        "download_url": "https://cdn.itqan.dev/qa.csv",
    }
    if structure is not None:
        result["structure"] = structure
    responses.add(responses.POST, f"{registry_url}/packages/resolve/manifest/", json={"results": [result]}, status=200)
    responses.add(responses.GET, "https://cdn.itqan.dev/qa.csv", body=b"surah,ayah,question\n", status=download_status)


def _install(runner: CliRunner, tmp_path: Path, registry_url: str):
    return runner.invoke(
        cli,
        [
            "install",
            "--manifest",
            str(tmp_path / "itqan-assets.yaml"),
            "--lockfile",
            str(tmp_path / "itqan-assets.lock"),
            "--assets-dir",
            str(tmp_path / "assets"),
            "--registry-url",
            registry_url,
        ],
    )


@responses.activate
def test_install_command_where_resolved_version_gained_a_column_should_refresh_columns_block(
    runner: CliRunner, tmp_path: Path
):
    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(QA_MANIFEST)
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    assert (tmp_path / "itqan-assets.yaml").read_text(encoding="utf-8") == (
        "schema_version: 1\n\nassets:\n"
        "  # itqan:columns CSV, one row per ayah: surah, ayah, question, answer, extra\n"
        "  # itqan:columns   question: Question\n"
        '  qa:\n    version: "^1.0.0"\n'
    )
    assert "Updated column notes in itqan-assets.yaml" in result.output


@responses.activate
def test_install_command_where_registry_reports_no_structure_should_leave_manifest_bytes_unchanged(
    runner: CliRunner, tmp_path: Path
):
    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(QA_MANIFEST)
    _mock_qa_resolve(registry_url, structure=None)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    assert (tmp_path / "itqan-assets.yaml").read_bytes() == QA_MANIFEST
    assert "column notes" not in result.output


@responses.activate
def test_install_command_where_download_fails_should_not_rewrite_manifest(runner: CliRunner, tmp_path: Path):
    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(QA_MANIFEST)
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE, download_status=500)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code != 0
    assert (tmp_path / "itqan-assets.yaml").read_bytes() == QA_MANIFEST


@responses.activate
def test_install_command_where_block_already_current_should_not_rewrite_manifest(runner: CliRunner, tmp_path: Path):
    registry_url = "https://api.itqan.dev/api"
    current = (
        b"schema_version: 1\n\nassets:\n"
        b"  # itqan:columns CSV, one row per ayah: surah, ayah, question, answer, extra\n"
        b"  # itqan:columns   question: Question\n"
        b'  qa:\n    version: "^1.0.0"\n'
    )
    manifest = tmp_path / "itqan-assets.yaml"
    manifest.write_bytes(current)
    before = manifest.stat().st_mtime_ns
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    assert manifest.read_bytes() == current
    assert manifest.stat().st_mtime_ns == before


@responses.activate
def test_install_command_where_manifest_uses_crlf_should_keep_crlf_when_refreshing(runner: CliRunner, tmp_path: Path):
    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(QA_MANIFEST.replace(b"\n", b"\r\n"))
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    raw = (tmp_path / "itqan-assets.yaml").read_bytes()
    assert b"itqan:columns CSV, one row per ayah: surah, ayah, question, answer, extra\r\n" in raw
    assert raw.count(b"\n") == raw.count(b"\r\n")


@responses.activate
def test_install_command_where_entry_name_differs_from_slug_should_refresh_that_entry(
    runner: CliRunner, tmp_path: Path
):
    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(
        b'schema_version: 1\n\nassets:\n  qa-en:\n    version: "^1.0.0"\n    asset: qa\n    language: en\n'
    )
    result = {
        "slug": "qa",
        "name": "qa-en",
        "asset_version_id": 7,
        "resolved_version": "1.1.0",
        "asset_name": "QA",
        "download_url": "https://cdn.itqan.dev/qa.csv",
        "structure": QA_STRUCTURE,
    }
    responses.add(responses.POST, f"{registry_url}/packages/resolve/manifest/", json={"results": [result]}, status=200)
    responses.add(responses.GET, "https://cdn.itqan.dev/qa.csv", body=b"surah,ayah,question\n", status=200)

    outcome = _install(runner, tmp_path, registry_url)

    assert outcome.exit_code == 0, outcome.output
    assert (
        (tmp_path / "itqan-assets.yaml")
        .read_text(encoding="utf-8")
        .startswith(
            "schema_version: 1\n\nassets:\n"
            "  # itqan:columns CSV, one row per ayah: surah, ayah, question, answer, extra\n"
            "  # itqan:columns   question: Question\n"
            "  qa-en:\n"
        )
    )


@responses.activate
def test_install_command_where_lockfile_fresh_should_still_refresh_columns_block(runner: CliRunner, tmp_path: Path):
    registry_url = "https://api.itqan.dev/api"
    manifest = tmp_path / "itqan-assets.yaml"
    manifest.write_bytes(QA_MANIFEST)
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)
    assert _install(runner, tmp_path, registry_url).exit_code == 0
    manifest.write_bytes(QA_MANIFEST)  # stale notes again; the entries are unchanged
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)

    result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    assert "Lockfile is FRESH" in result.output
    assert "question, answer, extra" in manifest.read_text(encoding="utf-8")


@responses.activate
def test_install_command_where_refresh_fails_should_warn_and_still_succeed(runner: CliRunner, tmp_path: Path):
    from unittest.mock import patch

    from itqan_cli import main as main_module
    from itqan_cli.columns_comment import refresh_blocks
    from itqan_cli.exceptions import ManifestError

    registry_url = "https://api.itqan.dev/api"
    (tmp_path / "itqan-assets.yaml").write_bytes(QA_MANIFEST)
    _mock_qa_resolve(registry_url, structure=QA_STRUCTURE)

    with patch.object(main_module, refresh_blocks.__name__, side_effect=ManifestError("bad")):
        result = _install(runner, tmp_path, registry_url)

    assert result.exit_code == 0, result.output
    assert "Could not update column notes" in result.output
    assert (tmp_path / "itqan-assets.yaml").read_bytes() == QA_MANIFEST

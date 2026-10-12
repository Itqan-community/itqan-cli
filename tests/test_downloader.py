"""Tests for AssetDownloader idempotency and atomic materialization."""

from pathlib import Path

import pytest
import responses

from itqan_cli.client import ResolvedAssetPayload
from itqan_cli.downloader import AssetDownloader
from itqan_cli.exceptions import DownloadError


@responses.activate
def test_materialize_asset_where_file_not_yet_present_should_download_then_skip_on_second_call(
    tmp_path: Path,
):
    assets_dir = tmp_path / "assets"
    downloader = AssetDownloader(assets_dir=assets_dir)

    asset = ResolvedAssetPayload(
        slug="quran-uthmani-hafs",
        asset_version_id=1,
        resolved_version="2.4.1",
        asset_name="Quran Hafs",
        download_url="https://cdn.itqan.dev/quran.zip",
    )

    responses.add(
        responses.GET,
        "https://cdn.itqan.dev/quran.zip",
        body=b"dummy zip content here",
        status=200,
    )

    # 1. First run: downloads file
    res1 = downloader.materialize_asset(asset)
    assert res1.downloaded is True
    assert res1.target_path.is_file()
    assert res1.target_path.read_bytes() == b"dummy zip content here"
    assert len(responses.calls) == 1

    # 2. Second run: idempotency (skips download)
    res2 = downloader.materialize_asset(asset)
    assert res2.downloaded is False
    assert len(responses.calls) == 1  # No second HTTP call made!


@responses.activate
def test_materialize_asset_where_server_returns_500_should_raise_download_error_and_leave_no_files(
    tmp_path: Path,
):
    assets_dir = tmp_path / "assets"
    downloader = AssetDownloader(assets_dir=assets_dir)

    asset = ResolvedAssetPayload(
        slug="failing-pkg",
        asset_version_id=2,
        resolved_version="1.0.0",
        asset_name="Failing Asset",
        download_url="https://cdn.itqan.dev/failing.zip",
    )

    responses.add(
        responses.GET,
        "https://cdn.itqan.dev/failing.zip",
        status=500,
    )

    with pytest.raises(DownloadError):
        downloader.materialize_asset(asset)

    # Verify no temp or target file left behind
    slug_dir = assets_dir / "failing-pkg"
    if slug_dir.exists():
        files = list(slug_dir.iterdir())
        assert len(files) == 0


@responses.activate
def test_materialize_asset_should_keep_the_version_marker_out_of_the_asset_folder(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    asset = ResolvedAssetPayload(
        slug="tafsir",
        asset_version_id=1,
        resolved_version="1.2.0",
        asset_name="T",
        download_url="https://cdn.itqan.dev/t.csv",
    )
    responses.add(responses.GET, "https://cdn.itqan.dev/t.csv", body=b"a,b", status=200)

    AssetDownloader(assets_dir=assets_dir).materialize_asset(asset)

    # Flutter bundles every file in a registered folder, so only the asset belongs there.
    assert [p.name for p in (assets_dir / "tafsir").iterdir()] == ["t.csv"]
    assert (assets_dir / ".itqan" / "tafsir").read_text() == "1.2.0"


@responses.activate
def test_materialize_asset_where_install_has_the_old_in_folder_marker_should_move_it_without_downloading(
    tmp_path: Path,
):
    assets_dir = tmp_path / "assets"
    (assets_dir / "tafsir").mkdir(parents=True)
    (assets_dir / "tafsir" / "t.csv").write_bytes(b"a,b")
    (assets_dir / "tafsir" / ".itqan_version").write_text("1.2.0")
    asset = ResolvedAssetPayload(
        slug="tafsir",
        asset_version_id=1,
        resolved_version="1.2.0",
        asset_name="T",
        download_url="https://cdn.itqan.dev/t.csv",
    )

    result = AssetDownloader(assets_dir=assets_dir).materialize_asset(asset)

    assert result.downloaded is False
    assert len(responses.calls) == 0
    assert not (assets_dir / "tafsir" / ".itqan_version").exists()
    assert (assets_dir / ".itqan" / "tafsir").read_text() == "1.2.0"


@responses.activate
def test_materialize_asset_where_old_marker_is_outdated_should_download_and_remove_it(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    (assets_dir / "tafsir").mkdir(parents=True)
    (assets_dir / "tafsir" / "t.csv").write_bytes(b"old")
    (assets_dir / "tafsir" / ".itqan_version").write_text("1.1.0")
    asset = ResolvedAssetPayload(
        slug="tafsir",
        asset_version_id=1,
        resolved_version="1.2.0",
        asset_name="T",
        download_url="https://cdn.itqan.dev/t.csv",
    )
    responses.add(responses.GET, "https://cdn.itqan.dev/t.csv", body=b"new", status=200)

    result = AssetDownloader(assets_dir=assets_dir).materialize_asset(asset)

    assert result.downloaded is True
    assert [p.name for p in (assets_dir / "tafsir").iterdir()] == ["t.csv"]
    assert (assets_dir / ".itqan" / "tafsir").read_text() == "1.2.0"


def test_materialize_asset_where_entry_is_named_like_the_marker_folder_should_raise(tmp_path: Path):
    asset = ResolvedAssetPayload(
        slug=".itqan",
        asset_version_id=1,
        resolved_version="1.0.0",
        asset_name="T",
        download_url="https://cdn.itqan.dev/t.csv",
    )

    with pytest.raises(DownloadError, match="reserved"):
        AssetDownloader(assets_dir=tmp_path).materialize_asset(asset)

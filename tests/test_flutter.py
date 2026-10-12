"""Tests for registering installed asset folders in a Flutter project's pubspec.yaml."""

import json
from pathlib import Path
import re

from click.testing import CliRunner
import pytest
import responses

from itqan_cli.exceptions import FlutterPubspecError
from itqan_cli.flutter import (
    BLOCK_END,
    BLOCK_START,
    asset_folders,
    has_managed_block,
    is_flutter_project,
    render,
    update_pubspec,
)
from itqan_cli.main import cli

# The tail of the pubspec `flutter create` writes, comments included.
TEMPLATE = """name: my_app
description: "A new Flutter project."

dependencies:
  flutter:
    sdk: flutter

  # The following adds the Cupertino Icons font to your application.
  cupertino_icons: ^1.0.8

# The following section is specific to Flutter packages.
flutter:

  # The following line ensures that the Material Icons font is
  # included with your application.
  uses-material-design: true

  # To add assets to your application, add an assets section, like this:
  # assets:
  #   - images/a_dot_burr.jpeg
"""

FOLDERS = ["assets/tafsir-jalalayn/", "assets/tafsir-jalalayn-en/"]


def block(indent: str, folders: list[str]) -> str:
    items = "".join(f"{indent}- {folder}\n" for folder in folders)
    return f"{indent}{BLOCK_START}\n{items}{indent}{BLOCK_END}\n"


def test_render_where_template_has_no_assets_key_should_add_one_right_under_flutter():
    result = render(TEMPLATE, FOLDERS)

    assert result == TEMPLATE.replace("flutter:\n\n", "flutter:\n  assets:\n" + block("    ", FOLDERS) + "\n", 1)


def test_render_where_assets_has_hand_written_entries_should_append_the_block_after_them():
    text = TEMPLATE + "  assets:\n    - images/   # the logo\n    - fonts/x.ttf\n\n  fonts: []\n"

    result = render(text, FOLDERS)

    expected = TEMPLATE + "  assets:\n    - images/   # the logo\n    - fonts/x.ttf\n"
    expected += block("    ", FOLDERS) + "\n  fonts: []\n"
    assert result == expected


def test_render_where_entries_are_mappings_with_flavors_should_append_after_the_whole_last_entry():
    text = "flutter:\n  assets:\n    - path: images/\n      flavors:\n        - prod\n  uses-material-design: true\n"

    result = render(text, FOLDERS)

    assert result == (
        "flutter:\n  assets:\n    - path: images/\n      flavors:\n        - prod\n"
        + block("    ", FOLDERS)
        + "  uses-material-design: true\n"
    )


def test_render_where_list_items_sit_at_the_key_indent_should_match_that_indent():
    text = "flutter:\n  assets:\n  - images/\n"

    assert render(text, FOLDERS) == "flutter:\n  assets:\n  - images/\n" + block("  ", FOLDERS)


def test_render_where_assets_key_is_empty_should_fill_it():
    text = "flutter:\n  assets:\n  uses-material-design: true\n"

    result = render(text, FOLDERS)

    assert result == "flutter:\n  assets:\n" + block("    ", FOLDERS) + "  uses-material-design: true\n"


def test_render_where_flutter_section_is_empty_should_add_assets_under_it():
    text = "name: app\nflutter:\n"

    assert render(text, FOLDERS) == "name: app\nflutter:\n  assets:\n" + block("    ", FOLDERS)


def test_render_where_block_exists_should_replace_only_its_entries():
    text = TEMPLATE + "  assets:\n    - images/\n" + block("    ", FOLDERS) + "    - fonts/\n"

    result = render(text, ["assets/tafsir-jalalayn/"])

    assert (
        result
        == TEMPLATE + "  assets:\n    - images/\n" + block("    ", ["assets/tafsir-jalalayn/"]) + "    - fonts/\n"
    )


def test_render_where_no_folders_should_keep_an_empty_block():
    text = "flutter:\n  assets:\n" + block("    ", FOLDERS)

    assert render(text, []) == "flutter:\n  assets:\n" + block("    ", [])


def test_render_where_path_needs_quoting_should_quote_it():
    result = render("flutter:\n", ["assets/a b#c/"])

    assert '    - "assets/a b#c/"\n' in result


def test_render_where_arabic_path_should_keep_it_plain():
    result = render("flutter:\n", ["assets/تفسير/"])

    assert "    - assets/تفسير/\n" in result


def test_render_where_file_has_no_trailing_newline_should_still_produce_valid_lines():
    result = render("flutter:\n  assets:\n    - images/", FOLDERS)

    assert result == "flutter:\n  assets:\n    - images/\n" + block("    ", FOLDERS)


@pytest.mark.parametrize(
    "text, message",
    [
        ("name: app\n", "no `flutter:` section"),
        ("flutter:\n  assets: [images/]\n", "block list"),
        ("flutter:\n  assets: images/\n", "block list"),
        ("flutter: {uses-material-design: true}\n", "block mapping"),
        ("- a\n", "not a YAML mapping"),
        ("flutter:\n  assets:\n    - [\n", "Could not parse"),
        ("flutter:\n  assets:\n    # itqan:start\n", "exactly one"),
        ("flutter:\n  assets:\n    # itqan:end\n    # itqan:start\n", "exactly one"),
    ],
)
def test_render_where_pubspec_cant_take_the_block_should_raise(text: str, message: str):
    with pytest.raises(FlutterPubspecError, match=message):
        render(text, FOLDERS)


def test_update_pubspec_where_run_twice_should_leave_the_file_byte_for_byte_identical(tmp_path: Path):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_text(TEMPLATE, encoding="utf-8")

    assert update_pubspec(pubspec, FOLDERS) is True
    first = pubspec.read_bytes()
    mtime = pubspec.stat().st_mtime_ns

    assert update_pubspec(pubspec, FOLDERS) is False
    assert pubspec.read_bytes() == first
    assert pubspec.stat().st_mtime_ns == mtime


def test_update_pubspec_where_file_uses_crlf_should_keep_crlf(tmp_path: Path):
    pubspec = tmp_path / "pubspec.yaml"
    pubspec.write_bytes(TEMPLATE.replace("\n", "\r\n").encode())

    update_pubspec(pubspec, FOLDERS)

    data = pubspec.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert has_managed_block(pubspec)


def test_update_pubspec_where_missing_should_raise(tmp_path: Path):
    with pytest.raises(FlutterPubspecError, match="No pubspec.yaml next to the manifest"):
        update_pubspec(tmp_path / "pubspec.yaml", FOLDERS)


def test_asset_folders_should_list_every_folder_with_files_including_nested_ones(tmp_path: Path):
    for path in [
        "assets/mushaf/pages/001.png",
        "assets/mushaf/index.json",
        "assets/mushaf/empty/.keep",
        "assets/tafsir/tafsir.csv",
        "assets/.itqan/tafsir",
        "assets/tafsir/.hidden/x",
    ]:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x")

    folders = asset_folders(tmp_path, [tmp_path / "assets/tafsir", tmp_path / "assets/mushaf"])

    assert folders == ["assets/mushaf/", "assets/mushaf/pages/", "assets/tafsir/"]


def test_asset_folders_where_folder_is_outside_the_project_should_raise(tmp_path: Path):
    outside = tmp_path / "shared/tafsir"
    outside.mkdir(parents=True)
    (outside / "tafsir.csv").write_text("x")
    (tmp_path / "app").mkdir()

    with pytest.raises(FlutterPubspecError, match="outside the Flutter project"):
        asset_folders(tmp_path / "app", [outside])


def test_is_flutter_project_should_need_a_top_level_flutter_section(tmp_path: Path):
    pubspec = tmp_path / "pubspec.yaml"
    assert not is_flutter_project(pubspec)
    pubspec.write_text("name: lib\ndependencies:\n  flutter:\n    sdk: flutter\n")
    assert not is_flutter_project(pubspec)
    pubspec.write_text(TEMPLATE)
    assert is_flutter_project(pubspec)


# --- `itqan install --flutter` end to end ---------------------------------------------------

REGISTRY = "https://registry.test"
MANIFEST = """schema_version: 1
assets:
  tafsir-jalalayn:
    version: "^1.0.0"
  tafsir-jalalayn-en:
    asset: tafsir-jalalayn
    language: en
    version: "^1.0.0"
"""


def _mock_registry() -> None:
    """A registry that resolves every requested entry to 1.0.0, with a CSV to download."""

    def resolve(request):
        names = json.loads(request.body)["assets"]
        results = [
            {
                "slug": spec.get("asset", name) if isinstance(spec, dict) else name,
                "name": name,
                "asset_version_id": 1,
                "resolved_version": "1.0.0",
                "asset_name": name,
                "download_url": f"https://cdn.test/{name}.csv",
            }
            for name, spec in names.items()
        ]
        return 200, {}, json.dumps({"results": results})

    responses.add_callback(responses.POST, f"{REGISTRY}/packages/resolve/manifest/", callback=resolve)
    responses.add(responses.GET, re.compile(r"https://cdn\.test/.*"), body=b"surah,ayah,text\n")


def _install(project: Path, *args: str):
    return CliRunner().invoke(
        cli,
        [
            "install",
            "--manifest",
            str(project / "itqan-assets.yaml"),
            "--lockfile",
            str(project / "itqan-assets.lock"),
            "--registry-url",
            REGISTRY,
            *args,
        ],
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "itqan-assets.yaml").write_text(MANIFEST, encoding="utf-8")
    (tmp_path / "pubspec.yaml").write_text(TEMPLATE, encoding="utf-8")
    return tmp_path


@responses.activate
def test_install_flutter_should_list_every_installed_folder_then_keep_it_in_sync(project: Path):
    _mock_registry()
    pubspec = project / "pubspec.yaml"

    result = _install(project, "--flutter")

    assert result.exit_code == 0, result.output
    assert "Updated" in result.output
    expected = TEMPLATE.replace(
        "flutter:\n\n",
        "flutter:\n  assets:\n" + block("    ", ["assets/tafsir-jalalayn-en/", "assets/tafsir-jalalayn/"]) + "\n",
        1,
    )
    assert pubspec.read_text(encoding="utf-8") == expected

    # Later installs need no flag (the block is the opt-in) and leave an up-to-date file alone.
    result = _install(project)
    assert result.exit_code == 0, result.output
    assert "already lists" in result.output
    assert pubspec.read_text(encoding="utf-8") == expected

    # An entry dropped from the manifest drops out of the pubspec.
    (project / "itqan-assets.yaml").write_text(MANIFEST.split("  tafsir-jalalayn-en:")[0], encoding="utf-8")
    result = _install(project)
    assert result.exit_code == 0, result.output
    assert pubspec.read_text(encoding="utf-8") == TEMPLATE.replace(
        "flutter:\n\n", "flutter:\n  assets:\n" + block("    ", ["assets/tafsir-jalalayn/"]) + "\n", 1
    )


@responses.activate
def test_install_without_flutter_flag_or_block_should_leave_pubspec_alone(project: Path):
    _mock_registry()

    result = _install(project)

    assert result.exit_code == 0, result.output
    assert (project / "pubspec.yaml").read_text(encoding="utf-8") == TEMPLATE


@responses.activate
def test_install_no_flutter_should_skip_an_existing_block(project: Path):
    _mock_registry()
    text = "flutter:\n  assets:\n" + block("    ", ["assets/old/"])
    (project / "pubspec.yaml").write_text(text, encoding="utf-8")

    result = _install(project, "--no-flutter")

    assert result.exit_code == 0, result.output
    assert (project / "pubspec.yaml").read_text(encoding="utf-8") == text


@responses.activate
def test_install_flutter_without_pubspec_should_fail_before_downloading(project: Path):
    _mock_registry()
    (project / "pubspec.yaml").unlink()

    result = _install(project, "--flutter")

    assert result.exit_code == 1
    assert "No pubspec.yaml next to the manifest" in result.output
    assert len(responses.calls) == 0
    assert not (project / "itqan-assets.lock").exists()


@responses.activate
def test_install_flutter_where_pubspec_has_no_flutter_section_should_explain(project: Path):
    _mock_registry()
    (project / "pubspec.yaml").write_text("name: a_dart_package\n", encoding="utf-8")

    result = _install(project, "--flutter")

    assert result.exit_code == 1
    assert "no `flutter:` section" in result.output
    assert len(responses.calls) == 0

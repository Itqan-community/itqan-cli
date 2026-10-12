"""Tests for scripts/dart_package.py, which builds the pub.dev package on each release."""

import importlib.util
from pathlib import Path
import sys

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))  # the script imports npm_packages from its own folder
_spec = importlib.util.spec_from_file_location("dart_package", _SCRIPTS / "dart_package.py")
dart_package = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dart_package)


@pytest.mark.parametrize(("version", "semver"), [("0.2.0", "0.2.0"), ("0.2.0rc1", "0.2.0-rc.1")])
def test_build_should_set_the_package_and_cli_versions(tmp_path: Path, version: str, semver: str):
    out = dart_package.build(version, tmp_path / "pkg")

    pubspec = (out / "pubspec.yaml").read_text()
    assert f"\nversion: {semver}\n" in pubspec
    assert "0.0.0-dev" not in pubspec
    assert f"const cliVersion = '{version}';" in (out / "lib/src/version.dart").read_text()
    assert (out / "CHANGELOG.md").read_text().startswith(f"## {semver}\n")
    assert (out / "LICENSE").is_file()
    assert (out / "bin/itqan.dart").is_file()
    assert not (out / ".dart_tool").exists()
    assert not (out / "pubspec.lock").exists()


def test_build_should_leave_the_source_untouched(tmp_path: Path):
    dart_package.build("0.2.0", tmp_path / "pkg")

    assert "\nversion: 0.0.0-dev\n" in (dart_package.SOURCE / "pubspec.yaml").read_text()
    assert not (dart_package.SOURCE / "CHANGELOG.md").exists()


def test_build_should_reject_a_version_pub_cannot_take(tmp_path: Path):
    with pytest.raises(ValueError):
        dart_package.build("0.2.0.post1", tmp_path / "pkg")

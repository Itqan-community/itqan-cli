"""Tests for scripts/npm_packages.py, which builds the npm packages on each release."""

import importlib.util
import json
from pathlib import Path
import re

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "npm_packages.py"
_spec = importlib.util.spec_from_file_location("npm_packages", _SCRIPT)
npm_packages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(npm_packages)

BINARIES = [
    "itqan-0.2.0rc1-macos-arm64",
    "itqan-0.2.0rc1-macos-x86_64",
    "itqan-0.2.0rc1-linux-arm64",
    "itqan-0.2.0rc1-linux-x86_64",
    "itqan-0.2.0rc1-windows-x86_64.exe",
]


@pytest.fixture
def binaries(tmp_path: Path) -> Path:
    folder = tmp_path / "bin"
    folder.mkdir()
    for name in BINARIES:
        (folder / name).write_bytes(name.encode())
    return folder


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.2.0", "0.2.0"), ("0.2.0a1", "0.2.0-alpha.1"), ("0.2.0b2", "0.2.0-beta.2"), ("1.0.0rc10", "1.0.0-rc.10")],
)
def test_npm_version_where_pep440_should_return_semver(version, expected):
    assert npm_packages.npm_version(version) == expected


def test_npm_version_where_unsupported_should_refuse():
    with pytest.raises(ValueError):
        npm_packages.npm_version("0.2.0.dev1")


def test_build_where_all_binaries_present_should_write_platform_packages_then_main(binaries: Path, tmp_path: Path):
    # Act
    folders = npm_packages.build("0.2.0rc1", binaries, tmp_path / "out")

    # Assert
    assert [folder.name for folder in folders] == [
        "cli-darwin-arm64",
        "cli-darwin-x64",
        "cli-linux-arm64",
        "cli-linux-x64",
        "cli-win32-x64",
        "itqan-cli",
    ]
    linux = json.loads((folders[3] / "package.json").read_text())
    assert linux["name"] == "@itqan-community/cli-linux-x64"
    assert linux["version"] == "0.2.0-rc.1"
    assert (linux["os"], linux["cpu"], linux["libc"]) == (["linux"], ["x64"], ["glibc"])
    binary = folders[3] / "bin" / "itqan"
    assert binary.read_bytes() == b"itqan-0.2.0rc1-linux-x86_64"
    assert binary.stat().st_mode & 0o111
    assert (folders[4] / "bin" / "itqan.exe").read_bytes() == b"itqan-0.2.0rc1-windows-x86_64.exe"

    main = json.loads((folders[5] / "package.json").read_text())
    assert main["bin"] == {"itqan": "bin/itqan.js", "itqan-cli": "bin/itqan.js"}
    assert main["optionalDependencies"] == {
        f"@itqan-community/cli-{platform}": "0.2.0-rc.1"
        for platform in ["darwin-arm64", "darwin-x64", "linux-arm64", "linux-x64", "win32-x64"]
    }
    assert (folders[5] / "bin" / "itqan.js").is_file()
    assert all((folder / "LICENSE").is_file() for folder in folders)


def test_build_where_binary_missing_should_refuse(binaries: Path, tmp_path: Path):
    # Arrange
    (binaries / "itqan-0.2.0rc1-linux-arm64").unlink()

    # Act / Assert
    with pytest.raises(FileNotFoundError, match="itqan-0.2.0rc1-linux-arm64"):
        npm_packages.build("0.2.0rc1", binaries, tmp_path / "out")


def test_shim_where_compared_with_script_should_name_the_same_platform_packages():
    # Arrange
    shim = (npm_packages.SHIM_DIR / "bin" / "itqan.js").read_text()

    # Act
    in_shim = dict(re.findall(r'"([a-z0-9]+-[a-z0-9]+)": "(@itqan-community/cli-[a-z0-9-]+)"', shim))

    # Assert
    assert in_shim == {f"{os}-{cpu}": npm_packages.platform_package_name(os, cpu) for os, cpu in npm_packages.PLATFORMS}

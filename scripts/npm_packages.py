"""Build the npm packages for a release from its standalone binaries.

    python scripts/npm_packages.py 0.2.0 bin/ npm-dist/

Writes one package per platform, holding that platform's binary (`@itqan-community/cli-<os>-<cpu>`,
limited by `os`/`cpu` so npm installs only the matching one), and the main `itqan-cli` package with
the `itqan` shim from npm/ and the platform packages as optional dependencies. Prints the package
folders in publishing order: platform packages first, `itqan-cli` last. release.yml runs this.
"""

import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SHIM_DIR = ROOT / "npm"
SCOPE = "@itqan-community"
REPOSITORY = {"type": "git", "url": "git+https://github.com/Itqan-community/itqan-cli.git"}

# npm (os, cpu) -> the binary's os-arch suffix (binaries.yml) and a readable name.
PLATFORMS = {
    ("darwin", "arm64"): ("macos-arm64", "macOS arm64"),
    ("darwin", "x64"): ("macos-x86_64", "macOS x86_64"),
    ("linux", "arm64"): ("linux-arm64", "Linux arm64"),
    ("linux", "x64"): ("linux-x86_64", "Linux x86_64"),
    ("win32", "x64"): ("windows-x86_64", "Windows x86_64"),
}

_PRERELEASE = {"a": "alpha", "b": "beta", "rc": "rc"}


def npm_version(version: str) -> str:
    """PEP 440 -> semver: `0.2.0` stays, `0.2.0rc1` becomes `0.2.0-rc.1`."""
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?", version)
    if not match:
        raise ValueError(f"can't publish version {version!r} to npm")
    release, kind, number = match.groups()
    return f"{release}-{_PRERELEASE[kind]}.{number}" if kind else release


def platform_package_name(os: str, cpu: str) -> str:
    return f"{SCOPE}/cli-{os}-{cpu}"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n")


def build(version: str, binaries: Path, out: Path) -> list[Path]:
    semver = npm_version(version)
    common = {
        "version": semver,
        "license": "MIT",
        "homepage": "https://github.com/Itqan-community/itqan-cli",
        "repository": REPOSITORY,
    }
    folders = []

    for (os, cpu), (suffix, label) in PLATFORMS.items():
        ext = ".exe" if os == "win32" else ""
        source = binaries / f"itqan-{version}-{suffix}{ext}"
        if not source.is_file():
            raise FileNotFoundError(f"{source} is missing")
        folder = out / f"cli-{os}-{cpu}"
        (folder / "bin").mkdir(parents=True)
        binary = folder / "bin" / f"itqan{ext}"
        shutil.copyfile(source, binary)
        binary.chmod(0o755)
        package = {
            "name": platform_package_name(os, cpu),
            "description": f"The itqan-cli binary for {label}.",
            **common,
            "os": [os],
            "cpu": [cpu],
            "files": ["bin"],
            "preferUnplugged": True,
        }
        if os == "linux":
            # Built against glibc (ubuntu-22.04), so it doesn't run on musl (Alpine).
            package["libc"] = ["glibc"]
        _write_json(folder / "package.json", package)
        shutil.copyfile(ROOT / "LICENSE", folder / "LICENSE")
        (folder / "README.md").write_text(
            f"# {package['name']}\n\nThe standalone `itqan` binary for {label}. Install "
            "[`itqan-cli`](https://www.npmjs.com/package/itqan-cli) instead, which picks the right one.\n"
        )
        folders.append(folder)

    main = out / "itqan-cli"
    shutil.copytree(SHIM_DIR, main)
    shutil.copyfile(ROOT / "LICENSE", main / "LICENSE")
    (main / "bin" / "itqan.js").chmod(0o755)
    _write_json(
        main / "package.json",
        {
            "name": "itqan-cli",
            "description": "Itqan Quranic Asset Manager: install and pin Itqan Quranic assets in your project.",
            **common,
            "keywords": ["itqan", "quran", "quranic", "tafsir", "mushaf", "assets", "cli"],
            "bin": {"itqan": "bin/itqan.js", "itqan-cli": "bin/itqan.js"},
            "files": ["bin"],
            "engines": {"node": ">=18"},
            "optionalDependencies": {platform_package_name(os, cpu): semver for os, cpu in PLATFORMS},
        },
    )
    folders.append(main)
    return folders


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    version, binaries, out = argv
    for folder in build(version, Path(binaries), Path(out)):
        print(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

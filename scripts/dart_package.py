"""Build the pub.dev package for a release.

    python scripts/dart_package.py 0.2.0 dart-build/

Copies the package in dart/ to the output folder with its version set: the pubspec gets the
release's semver version (`0.2.0`, or `0.2.0-rc.1` for `0.2.0rc1`) and lib/src/version.dart the
CLI version whose binary it downloads. Adds the LICENSE and a CHANGELOG.md linking the release
notes, which pub.dev expects. Prints the output folder. release.yml runs this.
"""

from pathlib import Path
import re
import shutil
import sys

from npm_packages import npm_version

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "dart"
PLACEHOLDER = "0.0.0-dev"


def _replace_once(path: Path, pattern: str, replacement: str) -> None:
    text, count = re.subn(pattern, replacement, path.read_text(encoding="utf-8"), count=1, flags=re.MULTILINE)
    if count != 1:
        raise ValueError(f"{path} has no {pattern!r} to set the version in")
    path.write_text(text, encoding="utf-8")


def build(version: str, out: Path) -> Path:
    semver = npm_version(version)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(SOURCE, out, ignore=shutil.ignore_patterns(".dart_tool", "pubspec.lock", "build"))
    _replace_once(out / "pubspec.yaml", rf"^version: {re.escape(PLACEHOLDER)}$", f"version: {semver}")
    _replace_once(out / "lib/src/version.dart", rf"'{re.escape(PLACEHOLDER)}'", f"'{version}'")
    shutil.copy(ROOT / "LICENSE", out / "LICENSE")
    (out / "CHANGELOG.md").write_text(
        f"## {semver}\n\nRuns itqan {version}. See the "
        f"[release notes](https://github.com/Itqan-community/itqan-cli/releases/tag/v{version}).\n",
        encoding="utf-8",
    )
    return out


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(build(sys.argv[1], Path(sys.argv[2])))

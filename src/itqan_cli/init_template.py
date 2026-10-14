"""Text of the starter itqan-assets.yaml written by `itqan init`."""

from __future__ import annotations

import json

from itqan_cli.client import CatalogLanguage, CatalogPackage
from itqan_cli.semver import parse_semver

SAMPLE_COUNT = 3

_HEADER = """\
# Itqan assets manifest: the Quranic data this project uses.
# Spec: https://github.com/Itqan-community/cms-backend/blob/main/docs/ASSET_MANIFEST.md
#
# After editing, run `itqan install` to download the assets and write
# itqan-assets.lock. Commit both files.

schema_version: 1

# Folder the assets are downloaded into, relative to this file.
assets_dir: {assets_dir}

# Each entry is a name (the asset's slug, unless the entry sets `asset`) and a
# version range:
#   "^1.2.0"  any 1.x from 1.2.0 on    "~1.2"  any 1.2.x    "1.2.0"  exactly 1.2.0
#
# Languages: an entry installs the asset's source language. Add
# `language: <code>` to install another one. To install several languages of
# the same asset, give each its own entry and point it at the asset with
# `asset: <slug>`. Each language has its own version history.
assets:
"""

_FALLBACK_ENTRIES = """\
  # {reason} so these are examples: replace the slugs with real ones
  # from the asset library at https://cms.itqan.dev, then uncomment.
  #
  # "tafsir-example":
  #   version: "^1.0.0"
  #
  # The same asset in English:
  # "tafsir-example-en":
  #   asset: "tafsir-example"
  #   language: "en"
  #   version: "^1.0.0"
"""


def _quote(value: str) -> str:
    """YAML double-quoted scalar; slugs like `true` or `123` must stay strings."""
    return json.dumps(value, ensure_ascii=False)


def _constraint(version: str) -> str:
    """`^latest`, except a prerelease, which only an exact pin can select."""
    semver = parse_semver(version)
    return version if semver is not None and semver.prerelease is not None else f"^{version}"


def _describe(language: CatalogLanguage) -> str:
    if not language.language:  # an asset whose source language code was never set
        return f"source ({language.latest_version})"
    source = "source, " if language.is_source else ""
    return f"{language.language} ({source}{language.latest_version})"


def entry_lines(
    name: str,
    version: str,
    *,
    asset: str | None = None,
    language: str | None = None,
    indent: str = "  ",
    constraint: str | None = None,
) -> list[str]:
    """One manifest entry under `assets:`, constrained to ``^version`` unless
    ``constraint`` is given; ``indent`` is the entry key's indentation, and its
    fields go one level deeper."""
    lines = [f"{indent}{_quote(name)}:"]
    if asset is not None:
        lines.append(f"{indent * 2}asset: {_quote(asset)}")
    if language is not None:
        lines.append(f"{indent * 2}language: {_quote(language)}")
    lines.append(f"{indent * 2}version: {_quote(constraint or _constraint(version))}")
    return lines


def render_header(assets_dir: str) -> str:
    """The starter file up to and including `assets:`, with no entries."""
    return _HEADER.format(assets_dir=_quote(assets_dir))


def pick_samples(packages: list[CatalogPackage], count: int = SAMPLE_COUNT) -> list[CatalogPackage]:
    """Up to ``count`` packages, leading with one that has several languages so
    the starter file shows a second-language entry."""
    usable = [package for package in packages if package.languages]
    multilingual = next((package for package in usable if len(package.languages) > 1), None)
    ordered = ([multilingual] if multilingual else []) + [package for package in usable if package is not multilingual]
    return ordered[:count]


_CATALOG_INTRO = """\
  # Examples from the catalog, commented out so nothing is installed until you
  # choose. Uncomment the ones you want, or run `itqan browse` to search the
  # catalog and add assets here.
"""


def _commented(lines: list[str], indent: str = "  ") -> list[str]:
    """``lines`` (entry lines at ``indent``) as YAML comments, keeping their nesting."""
    return [f"{indent}# {line[len(indent):]}" for line in lines]


def render_from_catalog(samples: list[CatalogPackage], assets_dir: str) -> str:
    """The starter file with ``samples`` as commented-out entries. At least one
    entry shows `language:`, even when no sample has a second language."""
    lines: list[str] = []
    names: set[str] = set()
    shows_language = False
    for package in samples:
        lines.append("")
        name = " ".join(package.name.split())  # one line, even if the name has newlines
        lines.append(f"  # {name} — languages: {', '.join(_describe(lang) for lang in package.languages)}")
        source = next((lang for lang in package.languages if lang.is_source), None)
        first = source or package.languages[0]
        other = next((lang for lang in package.languages if lang is not first), None)
        # Name the source language too when no other entry would show `language:`.
        language = first.language if source is None or (other is None and not shows_language) else None
        if not first.language:  # a source language without a code can't be named
            language = None
        lines += _commented(entry_lines(package.slug, first.latest_version, language=language))
        shows_language = shows_language or language is not None
        names.add(package.slug)
        entry_name = f"{package.slug}-{other.language}" if other else None
        if other is not None and entry_name not in names:
            lines.append(f"  # The same asset in another language ({other.language}):")
            lines += _commented(
                entry_lines(entry_name, other.latest_version, asset=package.slug, language=other.language)
            )
            names.add(entry_name)
            shows_language = True
    return render_header(assets_dir) + _CATALOG_INTRO + "\n".join(lines) + "\n"


def render_fallback(assets_dir: str, reason: str) -> str:
    return render_header(assets_dir) + _FALLBACK_ENTRIES.format(reason=reason)

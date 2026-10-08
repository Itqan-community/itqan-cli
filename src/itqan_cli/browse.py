"""`itqan browse`: list the registry's catalog and add picked assets to the manifest.

The pieces that decide what to show and what to write are plain functions;
only `pick_packages` and `pick_languages` talk to the terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from itqan_cli.client import CatalogLanguage, CatalogPackage
from itqan_cli.exceptions import ManifestError
from itqan_cli.init_template import entry_lines
from itqan_cli.manifest import AssetManifest, parse_manifest_content

# (asset slug, language code); None stands for the asset's source language.
Target = tuple[str, str | None]


@dataclass(frozen=True, slots=True)
class NewEntry:
    """A manifest entry `browse` is about to add."""

    name: str
    package: CatalogPackage
    language: CatalogLanguage

    def lines(self, indent: str) -> list[str]:
        if self.language.is_source:
            return entry_lines(self.name, self.language.latest_version, indent=indent)
        return entry_lines(
            self.name,
            self.language.latest_version,
            asset=self.package.slug,
            language=self.language.language,
            indent=indent,
        )


def manifest_targets(manifest: AssetManifest | None) -> set[Target]:
    if manifest is None:
        return set()
    return {(entry.asset or entry.slug, entry.language) for entry in manifest.assets.values()}


def is_declared(targets: set[Target], package: CatalogPackage, language: CatalogLanguage) -> bool:
    """Whether the manifest already installs this language of the package."""
    if (package.slug, language.language) in targets:
        return True
    return language.is_source and (package.slug, None) in targets


def missing_languages(targets: set[Target], package: CatalogPackage) -> list[CatalogLanguage]:
    return [lang for lang in package.languages if not is_declared(targets, package, lang)]


def plan_entries(
    picks: list[tuple[CatalogPackage, CatalogLanguage]], manifest: AssetManifest | None
) -> tuple[list[NewEntry], list[str]]:
    """Entries to add for the picked (package, language) pairs, and a warning
    for each pick that is skipped. The source language is named after the slug,
    another language `<slug>-<language>`, the same names `itqan init` uses."""
    targets = manifest_targets(manifest)
    taken = set(manifest.assets) if manifest is not None else set()
    entries: list[NewEntry] = []
    warnings: list[str] = []
    for package, language in picks:
        if is_declared(targets, package, language):
            warnings.append(f"{package.slug} ({language.language or 'source'}) is already in the manifest; skipped.")
            continue
        name = package.slug if language.is_source else f"{package.slug}-{language.language}"
        if name in taken:
            warnings.append(f"An entry named {name!r} already exists for another asset; skipped {package.slug}.")
            continue
        taken.add(name)
        targets.add((package.slug, None if language.is_source else language.language))
        entries.append(NewEntry(name=name, package=package, language=language))
    return entries, warnings


_ASSETS_KEY = re.compile(r"^assets[ \t]*:[ \t]*(#.*)?$")
_ENTRY_INDENT = re.compile(r"^([ \t]+)[^ \t#]")


def add_entries(content: str, entries: list[NewEntry]) -> str:
    """``content`` with ``entries`` appended to the end of its `assets:` block.

    Edits the text rather than re-dumping the YAML, so the file's comments and
    layout survive. New entries take the indentation of the existing ones.

    Raises:
        ManifestError when the file has no block-style `assets:` key or the
            result would not be a valid manifest.
    """
    lines = content.splitlines()
    start = next((i for i, line in enumerate(lines) if _ASSETS_KEY.match(line)), None)
    if start is None:
        raise ManifestError("Could not find a block-style `assets:` key to add entries under.")

    end = start  # last indented line of the block (entries or comments under it)
    indent: str | None = None
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip():
            continue
        if line[0] in " \t":
            end = i
            match = _ENTRY_INDENT.match(line)
            if indent is None and match:
                indent = match.group(1)
        elif not line.startswith("#"):
            break  # the next top-level key

    block: list[str] = []
    for entry in entries:
        name = " ".join(entry.package.name.split())
        block += ["", f"{indent or '  '}# {name} ({entry.language.language or 'source'})"]
        block += entry.lines(indent or "  ")
    if end == start:
        block = block[1:]  # first entry: no blank line right under `assets:`

    updated = "\n".join(lines[: end + 1] + block + lines[end + 1 :]) + "\n"
    manifest = parse_manifest_content(updated.encode("utf-8"))
    missing = [entry.name for entry in entries if entry.name not in manifest.assets]
    if missing:
        raise ManifestError(f"Could not add {', '.join(missing)} to the manifest's assets.")
    return updated


def _languages_text(package: CatalogPackage) -> str:
    return ",".join(lang.language or "source" for lang in package.languages)


def _latest_text(package: CatalogPackage) -> str:
    source = next((lang for lang in package.languages if lang.is_source), None)
    first = source or (package.languages[0] if package.languages else None)
    return first.latest_version if first else "-"


def render_table(packages: list[CatalogPackage], targets: set[Target]) -> str:
    """Plain-text listing for pipes, CI and `--no-interactive`."""
    header = ("SLUG", "CATEGORY", "LANGUAGES", "LATEST", "ACCESS", "NAME")
    rows = [header] + [
        (
            ("* " if not missing_languages(targets, package) else "") + package.slug,
            package.category,
            _languages_text(package),
            _latest_text(package),
            "open" if package.is_open_access else "api-key",
            " ".join(package.name.split()),
        )
        for package in packages
    ]
    widths = [max(len(row[col]) for row in rows) for col in range(len(header) - 1)]
    return "\n".join(
        "  ".join([cell.ljust(width) for cell, width in zip(row, widths)] + [row[-1]]) for row in rows
    )


def to_json(packages: list[CatalogPackage], targets: set[Target]) -> list[dict]:
    return [
        {
            "slug": package.slug,
            "name": package.name,
            "category": package.category,
            "is_open_access": package.is_open_access,
            "publisher_name": package.publisher_name,
            "languages": [
                {
                    "language": lang.language,
                    "is_source": lang.is_source,
                    "latest_version": lang.latest_version,
                    "in_manifest": is_declared(targets, package, lang),
                }
                for lang in package.languages
            ],
        }
        for package in packages
    ]


def choice_title(package: CatalogPackage, width: int) -> str:
    access = "" if package.is_open_access else "  [api key]"
    return (
        f"{package.slug.ljust(width)}  {package.category.ljust(11)}  "
        f"{_languages_text(package).ljust(8)}  {_latest_text(package).ljust(9)}  "
        f"{' '.join(package.name.split())}{access}"
    )


def unavailable_reason(package: CatalogPackage, targets: set[Target], has_api_key: bool) -> str | None:
    """Why a package can't be picked, or None when it can."""
    if not missing_languages(targets, package):
        return "in manifest"
    if not package.is_open_access and not has_api_key:
        return "needs an API key"
    return None


def pick_packages(
    packages: list[CatalogPackage], targets: set[Target], has_api_key: bool
) -> list[CatalogPackage] | None:
    """Fuzzy multi-select over the catalog; None when the user cancels."""
    import questionary

    width = max(len(package.slug) for package in packages)
    choices = [
        questionary.Choice(
            title=choice_title(package, width),
            value=package,
            disabled=unavailable_reason(package, targets, has_api_key),
        )
        for package in packages
    ]
    return questionary.checkbox(
        "Pick assets to add (type to search, space to select, enter to confirm):",
        choices=choices,
        use_search_filter=True,
        use_jk_keys=False,
        instruction="",
    ).ask()


def pick_languages(package: CatalogPackage, targets: set[Target]) -> list[CatalogLanguage] | None:
    """The languages to add for ``package``: asks only when there is a choice."""
    available = missing_languages(targets, package)
    if len(available) <= 1:
        return available
    import questionary

    preferred = next((lang for lang in available if lang.is_source), available[0])
    choices = [
        questionary.Choice(
            title=f"{lang.language or 'source'}{' (source)' if lang.is_source else ''}  {lang.latest_version}",
            value=lang,
            checked=lang is preferred,
        )
        for lang in available
    ]
    return questionary.checkbox(f"{package.slug}: which languages?", choices=choices).ask()

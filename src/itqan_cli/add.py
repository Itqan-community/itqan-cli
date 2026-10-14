"""`itqan add`: add assets to the manifest by name, like `uv add` or `npm install <pkg>`.

The pieces are plain functions; `main.add_command` does the I/O.
"""

from __future__ import annotations

import re

from itqan_cli.client import CatalogLanguage, CatalogPackage
from itqan_cli.exceptions import ItqanCliError, ManifestError
from itqan_cli.manifest import AssetManifest, parse_manifest_content
from itqan_cli.semver import parse_constraint


def parse_spec(spec: str) -> tuple[str, str | None]:
    """``slug`` or ``slug@range`` → (slug, range or None).

    Raises:
        ItqanCliError when the slug is empty or the range isn't valid.
    """
    slug, sep, constraint = spec.partition("@")
    slug = slug.strip()
    if not slug:
        raise ItqanCliError(f"Missing asset name in {spec!r}.")
    if not sep:
        return slug, None
    try:
        parse_constraint(constraint)
    except ValueError as exc:
        raise ItqanCliError(f"Invalid version range in {spec!r}: {exc}.") from exc
    return slug, constraint.strip()


def pick_language(package: CatalogPackage, language: str | None) -> CatalogLanguage:
    """The rendition to add: ``language``, or the source language when None.

    Raises:
        ItqanCliError when the asset has no such language.
    """
    if language is None:
        source = next((lang for lang in package.languages if lang.is_source), None)
        if source is not None:
            return source
        if package.languages:
            return package.languages[0]
    else:
        match = next((lang for lang in package.languages if lang.language == language), None)
        if match is not None:
            return match
    available = ", ".join(lang.language or "source" for lang in package.languages) or "none"
    raise ItqanCliError(f"{package.slug} is not available in {language or 'any language'}; it has: {available}.")


def existing_entry(manifest: AssetManifest | None, package: CatalogPackage, language: CatalogLanguage) -> str | None:
    """The name of the manifest entry that already installs this language of the package."""
    if manifest is None:
        return None
    for name, entry in manifest.assets.items():
        if (entry.asset or entry.slug) != package.slug:
            continue
        if entry.language == language.language or (entry.language is None and language.is_source):
            return name
    return None


_VERSION_LINE = re.compile(r"^(?P<indent>[ \t]+)version[ \t]*:.*$")


def set_entry_version(content: str, name: str, constraint: str) -> str:
    """``content`` with entry ``name``'s `version:` set to ``constraint``, leaving
    every other line as it is.

    Raises:
        ManifestError when the entry can't be found or the result is invalid.
    """
    lines = content.splitlines()
    key = re.compile(rf"^(?P<indent>[ \t]+)(\"{re.escape(name)}\"|'{re.escape(name)}'|{re.escape(name)})[ \t]*:")
    start = next((i for i, line in enumerate(lines) if key.match(line)), None)
    if start is None:
        raise ManifestError(f"Could not find the {name!r} entry to update.")
    key_indent = len(key.match(lines[start]).group("indent"))
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= key_indent:
            break  # the next entry or key
        match = _VERSION_LINE.match(line)
        if match:
            lines[i] = f'{match.group("indent")}version: "{constraint}"'
            updated = "\n".join(lines) + "\n"
            if parse_manifest_content(updated.encode("utf-8")).assets[name].version != constraint:
                raise ManifestError(f"Could not update the {name!r} entry's version.")
            return updated
    raise ManifestError(f"The {name!r} entry has no `version:` line to update.")

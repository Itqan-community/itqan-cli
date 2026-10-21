"""The `# itqan:columns` comment block above a manifest entry.

A translation or tafsir can have several text columns; the registry describes
the file (template, CSV header, columns with labels) as `structure`. The block
tells whoever reads the manifest what the downloaded CSV holds. Its format is
shared byte for byte with the registry's Dependabot (see the backend's
docs/ASSET_MANIFEST.md, "Column comment block"), so only lines carrying the
marker are ever replaced.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from itqan_cli.exceptions import ManifestError
from itqan_cli.manifest import parse_manifest_content

MARKER = "# itqan:columns"

_ASSETS_KEY = re.compile(r"^assets[ \t]*:[ \t]*(#.*)?$")


@dataclass(frozen=True, slots=True)
class PackageColumn:
    key: str
    label_en: str = ""
    label_ar: str = ""


@dataclass(frozen=True, slots=True)
class PackageStructure:
    """A version's CSV layout: what one row is, its header and its text columns."""

    template: str
    header: tuple[str, ...]
    columns: tuple[PackageColumn, ...]


def _one_line(value: str) -> str:
    """``value`` with every run of whitespace (newlines included) as one space: a
    publisher-typed label must never become a line of YAML of its own."""
    return " ".join(value.split())


def render_block(structure: PackageStructure, indent: str) -> list[str]:
    """The block's lines at ``indent``; none for a single-column asset."""
    if len(structure.columns) <= 1:
        return []
    header = ", ".join(_one_line(name) for name in structure.header)
    lines = [f"{indent}{MARKER} CSV, one row per {_one_line(structure.template)}: {header}"]
    for column in structure.columns:
        labels = " / ".join(_one_line(label) for label in (column.label_en, column.label_ar) if _one_line(label))
        if labels:
            lines.append(f"{indent}{MARKER}   {_one_line(column.key)}: {labels}")
    return lines


def _entry_key(name: str) -> re.Pattern[str]:
    """A block-style key line for ``name`` (bare or quoted); flow entries don't match."""
    quoted = re.escape(name)
    return re.compile(rf"^(?P<indent>[ \t]+)(\"{quoted}\"|'{quoted}'|{quoted})[ \t]*:[ \t]*(#.*)?$")


def _find_entry(lines: list[str], name: str) -> int | None:
    start = next((i for i, line in enumerate(lines) if _ASSETS_KEY.match(line)), None)
    if start is None:
        return None
    key = _entry_key(name)
    return next((i for i in range(start + 1, len(lines)) if key.match(lines[i])), None)


def entry_indent(content: str, name: str) -> str | None:
    """The indentation of entry ``name``'s key line, or None when it isn't a block entry."""
    lines = content.split("\n")
    index = _find_entry(lines, name)
    if index is None:
        return None
    return _entry_key(name).match(lines[index]).group("indent")


def replace_block(content: str, name: str, block: list[str]) -> str:
    """``content`` with the marker lines directly above entry ``name`` replaced by
    ``block`` (``[]`` removes them). Every other line is kept as it is; a flow-style
    or missing entry leaves ``content`` unchanged.

    Raises:
        ManifestError when the result would not be a valid manifest.
    """
    lines = content.split("\n")
    index = _find_entry(lines, name)
    if index is None:
        return content
    start = index
    while start > 0 and lines[start - 1].lstrip().startswith(MARKER):
        start -= 1
    updated = "\n".join(lines[:start] + block + lines[index:])
    if updated == content:
        return content
    try:
        parse_manifest_content(updated.encode("utf-8"))
    except ManifestError as exc:
        raise ManifestError(f"Could not update the column notes of {name!r}: {exc}") from exc
    return updated


def refresh_blocks(content: str, payloads: list) -> str:
    """``content`` with each resolved entry's block matching its resolved version.

    Entries whose registry reported no ``structure`` (older registries, other
    categories) are left exactly as they are.
    """
    for payload in payloads:
        if payload.structure is None:
            continue
        indent = entry_indent(content, payload.entry_name)
        if indent is None:
            continue
        content = replace_block(content, payload.entry_name, render_block(payload.structure, indent))
    return content

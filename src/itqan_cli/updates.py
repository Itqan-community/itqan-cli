"""Newer versions of installed assets, as the registry reports them on resolve."""

from __future__ import annotations

from dataclasses import dataclass

from itqan_cli.client import ResolvedAssetPayload
from itqan_cli.semver import SemVer, matches_constraint, parse_constraint, parse_semver


@dataclass(frozen=True, slots=True)
class AssetUpdate:
    """``in_range``: a newer version the manifest's range allows, which
    `itqan install --force` installs. ``beyond_range``: a newer version the range
    doesn't allow, which needs a manifest change. Either may be None."""

    name: str
    installed: str
    in_range: str | None
    beyond_range: str | None


def find_updates(payloads: list[ResolvedAssetPayload], constraints: dict[str, str]) -> list[AssetUpdate]:
    """The entries of ``payloads`` with a newer version, in their order.

    ``constraints`` maps entry name to its manifest range. A registry that
    doesn't report newer versions yields no updates.
    """
    updates: list[AssetUpdate] = []
    for item in payloads:
        installed = parse_semver(item.resolved_version)
        if installed is None:
            continue
        in_range = _newer(item.latest_in_range, installed)
        newest_allowed = parse_semver(in_range) if in_range else installed
        beyond = _newer(item.latest_version, newest_allowed)
        if beyond is not None and _allows(constraints.get(item.entry_name), beyond):
            beyond = None  # the range allows it; latest_in_range already covers it
        if in_range or beyond:
            updates.append(AssetUpdate(item.entry_name, item.resolved_version, in_range, beyond))
    return updates


def summary_lines(updates: list[AssetUpdate]) -> list[str]:
    """One line per kind of update, saying what to run; empty when there are none."""
    lines: list[str] = []
    in_range = sum(1 for update in updates if update.in_range)
    beyond = sum(1 for update in updates if update.beyond_range)
    if in_range:
        lines.append(
            f"{_count(in_range)} a newer version within your manifest's range: "
            "run `itqan install --force` to update."
        )
    if beyond:
        lines.append(f"{_count(beyond)} a newer version outside your manifest's range: run `itqan outdated` to see.")
    return lines


def _count(n: int) -> str:
    return "1 asset has" if n == 1 else f"{n} assets have"


def _newer(version: str | None, than: SemVer | None) -> str | None:
    """``version`` when it parses and is newer than ``than``."""
    parsed = parse_semver(version) if version else None
    if parsed is None or than is None or not parsed > than:
        return None
    return version


def _allows(constraint: str | None, version: str) -> bool:
    if not constraint:
        return False
    try:
        return matches_constraint(parse_semver(version), parse_constraint(constraint))
    except ValueError:
        return False


def render_table(updates: list[AssetUpdate]) -> str:
    """``updates`` as an aligned table: installed, newest in range, newest overall."""
    rows = [("Entry", "Installed", "In range", "Latest")]
    rows += [
        (u.name, u.installed, u.in_range or u.installed, u.beyond_range or u.in_range or u.installed) for u in updates
    ]
    widths = [max(len(row[i]) for row in rows) for i in range(3)]
    return "\n".join("  ".join([cell.ljust(width) for cell, width in zip(row, widths)] + [row[-1]]) for row in rows)

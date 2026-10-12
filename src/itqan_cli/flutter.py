"""Register installed asset folders under `flutter: assets:` in a Flutter project's pubspec.yaml.

Flutter bundles only the files directly in a declared folder, not its subfolders, so every
folder holding installed files gets its own entry. The entries live in a marked block:

    flutter:
      assets:
        - images/                 # the developer's own entries are never touched
        # itqan:start (managed by `itqan install`, do not edit)
        - assets/tafsir-jalalayn/
        # itqan:end

The file is edited as text at positions taken from the YAML parser, so everything outside the
block keeps its comments and formatting byte for byte.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

import yaml

from itqan_cli.exceptions import FlutterPubspecError

PUBSPEC = "pubspec.yaml"
BLOCK_START = "# itqan:start (managed by `itqan install`, do not edit)"
BLOCK_END = "# itqan:end"
_START_RE = re.compile(r"^(\s*)# itqan:start\b")
_END_RE = re.compile(r"^\s*# itqan:end\b")
_PLAIN_PATH_RE = re.compile(r"^[\w./-]+$")


def has_managed_block(pubspec: Path) -> bool:
    """Whether pubspec.yaml already holds the block, i.e. the project opted in earlier."""
    if not pubspec.is_file():
        return False
    return any(_START_RE.match(line) for line in pubspec.read_text(encoding="utf-8").splitlines())


def is_flutter_project(pubspec: Path) -> bool:
    """Whether pubspec.yaml exists and has a top-level `flutter:` section."""
    if not pubspec.is_file():
        return False
    return any(re.match(r"^flutter\s*:", line) for line in pubspec.read_text(encoding="utf-8").splitlines())


def asset_folders(project_dir: Path, entry_dirs: list[Path]) -> list[str]:
    """Pubspec entries for every folder under ``entry_dirs`` that holds a file, relative to
    ``project_dir``, with forward slashes and a trailing slash, sorted."""
    root = project_dir.resolve()
    folders: set[str] = set()
    for entry_dir in entry_dirs:
        for dirpath, dirnames, filenames in os.walk(entry_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            if not any(not f.startswith(".") for f in filenames):
                continue
            folder = Path(dirpath).resolve()
            try:
                relative = folder.relative_to(root)
            except ValueError:
                raise FlutterPubspecError(
                    f"{folder} is outside the Flutter project in {root}, so Flutter can't bundle it. "
                    "Install the assets into a folder inside the project."
                ) from None
            folders.add(relative.as_posix() + "/")
    return sorted(folders)


def check_pubspec(pubspec: Path) -> None:
    """Raise if ``update_pubspec`` would fail, so it fails before anything is downloaded."""
    render(_read(pubspec).replace("\r\n", "\n"), [])


def update_pubspec(pubspec: Path, folders: list[str]) -> bool:
    """Make the managed block list exactly ``folders``. Returns whether the file changed."""
    raw = _read(pubspec)
    newline = "\r\n" if "\r\n" in raw else "\n"
    updated = render(raw.replace("\r\n", "\n"), folders)
    if newline != "\n":
        updated = updated.replace("\n", newline)
    if updated == raw:
        return False
    pubspec.write_bytes(updated.encode("utf-8"))
    return True


def _read(pubspec: Path) -> str:
    if not pubspec.is_file():
        raise FlutterPubspecError(
            f"No {PUBSPEC} next to the manifest, at {pubspec}. "
            f"--flutter needs itqan-assets.yaml in the Flutter project's folder, beside {PUBSPEC}."
        )
    return pubspec.read_bytes().decode("utf-8")


def render(text: str, folders: list[str]) -> str:
    """``text`` (a pubspec with "\\n" line endings) with the managed block listing ``folders``."""
    lines = text.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"

    starts = [i for i, line in enumerate(lines) if _START_RE.match(line)]
    ends = [i for i, line in enumerate(lines) if _END_RE.match(line)]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
            raise FlutterPubspecError(
                f"{PUBSPEC} needs exactly one `# itqan:start` line followed by one `# itqan:end` line."
            )
        indent = _START_RE.match(lines[starts[0]]).group(1)  # type: ignore[union-attr]
        new = lines[: starts[0]] + _block(indent, folders) + lines[ends[0] + 1 :]
    else:
        at, indent, prefix = _insertion_point(text)
        new = lines[:at] + prefix + _block(indent, folders) + lines[at:]
    return "".join(new)


def _block(indent: str, folders: list[str]) -> list[str]:
    items = [f"{indent}- {_quote(folder)}\n" for folder in folders]
    return [f"{indent}{BLOCK_START}\n", *items, f"{indent}{BLOCK_END}\n"]


def _quote(path: str) -> str:
    return path if _PLAIN_PATH_RE.match(path) else json.dumps(path, ensure_ascii=False)


def _insertion_point(text: str) -> tuple[int, str, list[str]]:
    """Where a new block goes: (line index to insert before, item indent, lines to add before
    the block, such as a new `assets:` key)."""
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise FlutterPubspecError(f"Could not parse {PUBSPEC}: {exc}") from exc
    if not isinstance(root, yaml.MappingNode):
        raise FlutterPubspecError(f"{PUBSPEC} is not a YAML mapping.")

    flutter_key, flutter = _get(root, "flutter")
    if flutter_key is None:
        raise FlutterPubspecError(f"{PUBSPEC} has no `flutter:` section. Is this a Flutter project?")
    key_line = flutter_key.start_mark.line
    key_col = flutter_key.start_mark.column
    if _is_null(flutter):
        child = " " * (key_col + 2)
        return key_line + 1, child + "  ", [f"{child}assets:\n"]
    if not isinstance(flutter, yaml.MappingNode) or flutter.flow_style:
        raise FlutterPubspecError(f"`flutter:` in {PUBSPEC} must be a block mapping to add assets to.")

    assets_key, assets = _get(flutter, "assets")
    if assets_key is None:
        child = " " * flutter.value[0][0].start_mark.column
        return key_line + 1, child + "  ", [f"{child}assets:\n"]
    if _is_null(assets):
        return assets_key.start_mark.line + 1, " " * (assets_key.start_mark.column + 2), []
    if not isinstance(assets, yaml.SequenceNode) or assets.flow_style:
        raise FlutterPubspecError(
            f"`flutter: assets:` in {PUBSPEC} must be a block list (one `- path` per line) to add assets to."
        )
    lines = text.splitlines()
    first_line = lines[assets.value[0].start_mark.line]
    indent = first_line[: len(first_line) - len(first_line.lstrip())]
    return _last_line(assets.value[-1]) + 1, indent, []


def _last_line(node: yaml.Node) -> int:
    """The line a node's text ends on. A block collection's end mark is the start of the next
    token, possibly lines later, so follow it down to its last scalar or flow collection."""
    while isinstance(node, (yaml.MappingNode, yaml.SequenceNode)) and not node.flow_style and node.value:
        last = node.value[-1]
        node = last[1] if isinstance(last, tuple) else last
    return node.end_mark.line


def _get(mapping: yaml.MappingNode, key: str) -> tuple[yaml.Node | None, yaml.Node | None]:
    for key_node, value_node in mapping.value:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == key:
            return key_node, value_node
    return None, None


def _is_null(node: yaml.Node) -> bool:
    """An empty value (`key:` with nothing after it), not an explicit `null` or `~`."""
    return isinstance(node, yaml.ScalarNode) and node.tag == "tag:yaml.org,2002:null" and node.value == ""

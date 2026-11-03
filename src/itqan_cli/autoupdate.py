"""`itqan autoupdate`: write a GitHub Actions workflow that opens a pull request for asset updates.

The workflow runs `itqan install --force` on a schedule, from the same folder and with the same
manifest and lockfile options the user would use locally, and hands any lockfile change to
peter-evans/create-pull-request, which opens the pull request or updates the open one.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import shlex

from itqan_cli.exceptions import ItqanCliError

DEFAULT_SCHEDULE = "0 6 * * 1"  # every Monday at 06:00 UTC
WORKFLOW_FILE = "update-itqan-assets.yml"
PR_BRANCH = "itqan/update-assets"

_CRON_FIELD_RE = re.compile(r"^[0-9A-Za-z*/,\-]+$")


def find_repo_root(start: Path) -> Path | None:
    """The nearest folder at or above ``start`` with a `.git` (a folder, or a file in a worktree)."""
    start = start.resolve()
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def validate_schedule(schedule: str) -> str:
    """A five-field cron expression, as GitHub's `on.schedule` takes it."""
    fields = schedule.split()
    if len(fields) != 5 or not all(_CRON_FIELD_RE.match(f) for f in fields):
        raise ItqanCliError(
            f"--schedule must be a cron expression with five fields, such as {DEFAULT_SCHEDULE!r}; got {schedule!r}."
        )
    return " ".join(fields)


def relative_to_root(path: Path, root: Path, what: str) -> PurePosixPath:
    """``path`` as a forward-slash path relative to the repository root, which is what a workflow sees."""
    try:
        return PurePosixPath(path.resolve().relative_to(root).as_posix())
    except ValueError:
        raise ItqanCliError(f"The {what} {path} is outside the repository at {root}.") from None


def _quote(value: str) -> str:
    """A double-quoted YAML scalar."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_workflow(*, install_args: list[str], working_directory: str, schedule: str) -> str:
    """The workflow file's text.

    ``install_args`` follow `itqan install`, ``working_directory`` is the folder (relative to the
    repository root) the command runs in, "." for the root.
    """
    command = shlex.join(["itqan", "install", *install_args])
    workdir = "" if working_directory == "." else f"        working-directory: {_quote(working_directory)}\n"
    body = f"`{command}` found newer versions allowed by the manifest."
    return f"""\
# Written by `itqan autoupdate`. Runs `itqan install --force` on a schedule and opens a pull
# request (or updates the open one) when that picks newer versions allowed by the manifest.
name: Update Itqan assets

on:
  schedule:
    - cron: {_quote(schedule)}
  workflow_dispatch:  # and whenever you run it by hand

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: itqan-community/setup-itqan@v1
      - run: {_quote(command)}
{workdir}        env:
          ITQAN_API_KEY: ${{{{ secrets.ITQAN_API_KEY }}}}  # only needed for assets that need access approval
      - uses: peter-evans/create-pull-request@v8
        with:
          branch: {PR_BRANCH}
          commit-message: "chore: update Itqan assets"
          title: "Update Itqan assets"
          body: {_quote(body)}
"""

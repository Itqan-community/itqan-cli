"""Headers that let the registry count CLI usage, sent with every request.

- ``User-Agent: itqan-cli/<version>``: always.
- ``X-Itqan-Install-Id: <uuid4>``: a random ID made on first use and kept in
  ``<config dir>/install-id``, so the registry can count installs of the CLI
  without knowing who runs it. Left out when it can't be stored.
- ``X-Itqan-Command: <command>``: the command that made the request, as
  ``itqan --help`` lists it (``sync`` is sent as ``install``). The registry
  doesn't count asset installs for ``outdated``, the one command that only
  checks versions.

``DO_NOT_TRACK`` or ``ITQAN_NO_TELEMETRY`` set to anything but ``0`` or
``false`` leaves out the last two, and no install-id file is made.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import tempfile
import uuid

import click

from itqan_cli.credentials import config_dir

_OPT_OUT_VARS = ("DO_NOT_TRACK", "ITQAN_NO_TELEMETRY")


def cli_version() -> str:
    try:
        return version("itqan-cli")
    except PackageNotFoundError:  # running from a source checkout that isn't installed
        return "unknown"


def user_agent() -> str:
    return f"itqan-cli/{cli_version()}"


def telemetry_disabled() -> bool:
    """True when an opt-out variable is set to anything but empty, ``0`` or ``false``."""
    return any(os.environ.get(var, "").strip().lower() not in ("", "0", "false") for var in _OPT_OUT_VARS)


def install_id_path() -> Path:
    return config_dir() / "install-id"


def install_id() -> str | None:
    """This installation's ID, made and stored on first use. A missing or corrupt file
    gets a new ID; None when it can't be stored, so the CLI carries on without one."""
    try:
        path = install_id_path()
    except RuntimeError:  # no home directory to put the config dir in
        return None
    try:
        return str(uuid.UUID(path.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):  # missing, unreadable, not text, or not a UUID
        pass
    new_id = str(uuid.uuid4())
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".install-id_", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new_id + "\n")
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError:
        return None
    return new_id


def current_command() -> str | None:
    """The `itqan` subcommand running now, or None outside one."""
    ctx = click.get_current_context(silent=True)
    if ctx is None or ctx.parent is None:
        return None
    while ctx.parent.parent is not None:
        ctx = ctx.parent
    return ctx.command.name


def usage_headers() -> dict[str, str]:
    """The headers to send with a request: see the module docstring."""
    headers = {"User-Agent": user_agent()}
    if telemetry_disabled():
        return headers
    if install := install_id():
        headers["X-Itqan-Install-Id"] = install
    if command := current_command():
        headers["X-Itqan-Command"] = command
    return headers

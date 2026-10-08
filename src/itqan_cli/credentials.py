"""API keys saved by `itqan login`, one per registry URL.

Keys live in ``<config dir>/credentials`` (JSON), readable only by the owner.
The config dir is ``$ITQAN_CONFIG_DIR``, else ``%APPDATA%\\itqan`` on Windows,
else ``$XDG_CONFIG_HOME/itqan`` or ``~/.config/itqan``. Keys are stored per
registry so a production key is never sent to a staging or local registry.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from itqan_cli.exceptions import ItqanCliError


class CredentialsError(ItqanCliError):
    """The credentials file can't be read or written."""


def config_dir() -> Path:
    if override := os.environ.get("ITQAN_CONFIG_DIR"):
        return Path(override)
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "itqan"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "itqan"


def credentials_path() -> Path:
    return config_dir() / "credentials"


def _registry_key(registry_url: str) -> str:
    return registry_url.rstrip("/")


def _read() -> dict:
    path = credentials_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CredentialsError(f"Could not read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("registries", {}), dict):
        raise CredentialsError(f"{path} is not a valid credentials file; delete it and run `itqan login` again.")
    return data


def _write(data: dict) -> None:
    """Replace the file atomically, created with owner-only permissions."""
    path = credentials_path()
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".credentials_", dir=path.parent)  # mkstemp creates it 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise CredentialsError(f"Could not write {path}: {exc}") from exc


def load_api_key(registry_url: str) -> str | None:
    """The key saved for ``registry_url``, or None."""
    entry = _read().get("registries", {}).get(_registry_key(registry_url))
    key = entry.get("api_key") if isinstance(entry, dict) else None
    return key if isinstance(key, str) and key else None


def save_api_key(registry_url: str, api_key: str) -> Path:
    data = _read()
    data.setdefault("registries", {})[_registry_key(registry_url)] = {"api_key": api_key}
    _write(data)
    return credentials_path()


def delete_api_key(registry_url: str) -> bool:
    """Forget the key for ``registry_url``; False when none was saved."""
    data = _read()
    if data.get("registries", {}).pop(_registry_key(registry_url), None) is None:
        return False
    _write(data)
    return True

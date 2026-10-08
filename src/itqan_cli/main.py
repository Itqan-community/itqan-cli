"""Itqan CLI entrypoint implementing `itqan install`, `sync`, `init` and `browse`."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import click

from itqan_cli import browse, credentials
from itqan_cli.client import DEFAULT_REGISTRY_URL, CatalogLanguage, CatalogPackage, RegistryClient, ResolvedAssetPayload
from itqan_cli.downloader import AssetDownloader
from itqan_cli.exceptions import ItqanCliError, RegistryApiError
from itqan_cli.init_template import pick_samples, render_fallback, render_from_catalog, render_header
from itqan_cli.lockfile import (
    AssetLockfile,
    LockfileEntry,
    LockfileState,
    evaluate_lockfile_state,
    serialize_lockfile,
)
from itqan_cli.manifest import AssetManifest, load_manifest, parse_manifest_content, validate_assets_dir

DEFAULT_ASSETS_DIR = "assets"


@click.group()
@click.version_option(package_name="itqan-cli", prog_name="itqan")
def cli() -> None:
    """Itqan Quranic Asset Manager.

    Install and pin Itqan Quranic assets in your project.
    """


def _run_install(
    manifest_path: str,
    lockfile_path: str,
    assets_dir: str | None,
    registry_url: str,
    api_key: str | None,
    force: bool,
) -> int:
    m_path = Path(manifest_path)
    l_path = Path(lockfile_path)

    click.echo(f"Evaluating asset declarations in {m_path}...")
    state, manifest, lockfile = evaluate_lockfile_state(m_path, l_path)

    if state == LockfileState.ABSENT:
        click.echo(f"No manifest found at {m_path}. Nothing to install.", err=True)
        return 1

    if state == LockfileState.INVALID:
        click.echo("Error: Manifest or lockfile is invalid or malformed.", err=True)
        return 1

    if state == LockfileState.ORPHAN:
        click.echo(f"Error: Lockfile exists at {l_path} but manifest {m_path} is missing.", err=True)
        return 1

    # --assets-dir wins; otherwise the manifest's assets_dir, else "assets",
    # both relative to the manifest's folder.
    assert manifest is not None
    a_dir = Path(assets_dir) if assets_dir else m_path.parent / (manifest.assets_dir or DEFAULT_ASSETS_DIR)

    client = RegistryClient(base_url=registry_url, api_key=api_key)
    downloader = AssetDownloader(assets_dir=a_dir)

    resolved_payloads: list[ResolvedAssetPayload] = []

    if state == LockfileState.FRESH and not force:
        assert lockfile is not None
        assert manifest is not None
        click.echo("Lockfile is FRESH. Installing locked versions...")
        # In FRESH mode, we query the registry with the locked exact pins
        locked_requests = {
            slug: manifest.assets[slug].to_request(version=entry.version) for slug, entry in lockfile.assets.items()
        }
        resolved_payloads = client.resolve_manifest(locked_requests)
    else:
        # MISSING or STALE or force: Resolve against declared constraints
        assert manifest is not None
        if state == LockfileState.STALE:
            click.echo("Lockfile is STALE. Re-resolving against manifest...")
        else:
            click.echo("Resolving declared assets against package registry...")

        resolved_payloads = client.resolve_manifest(manifest.registry_requests)

        # Build the new lockfile in memory — do NOT write it yet.
        # We only commit the lockfile after every asset has been downloaded
        # successfully. This ensures the lockfile always reflects reality:
        # if a download fails halfway, the old lockfile is preserved.
        new_lock_entries: dict[str, LockfileEntry] = {}
        for item in resolved_payloads:
            declared = manifest.assets[item.entry_name]
            new_lock_entries[item.entry_name] = LockfileEntry(
                slug=item.entry_name,
                constraint=declared.version,
                version=item.resolved_version,
                asset=declared.asset if declared.asset != item.entry_name else None,
                language=declared.language,
            )

        new_lockfile = AssetLockfile(
            lockfile_version=1,
            manifest_schema_version=manifest.schema_version,
            assets=new_lock_entries,
        )
        pending_lockfile_bytes = serialize_lockfile(new_lockfile)

    # --- Materialize assets BEFORE writing the lockfile ---
    # If any download fails, we raise immediately and the lockfile is untouched.
    click.echo(f"Materializing {len(resolved_payloads)} asset(s) into {a_dir}...")
    download_summary = []

    for item in resolved_payloads:
        res = downloader.materialize_asset(item, force=force)
        status_str = "downloaded" if res.downloaded else "cached (up-to-date)"
        click.echo(f"  * {res.slug} [{res.version}]: {status_str} -> {res.target_path}")
        download_summary.append(res)

    # --- All downloads succeeded: now atomically write the lockfile ---
    if state != LockfileState.FRESH or force:
        # Write to a sibling temp file then rename — prevents a partial write
        # from leaving a corrupt lockfile if the process is interrupted.
        tmp_fd, tmp_path_str = __import__("tempfile").mkstemp(
            prefix=".itqan_assets_lock_",
            suffix=".tmp",
            dir=l_path.parent,
        )
        tmp_lock = Path(tmp_path_str)
        try:
            with open(tmp_fd, "wb") as f:
                f.write(pending_lockfile_bytes)
            os.replace(tmp_lock, l_path)
            click.echo(f"Updated lockfile at {l_path}")
        except Exception:
            try:
                tmp_lock.unlink()
            except OSError:
                pass
            raise

    click.echo(f"Success! {len(download_summary)} asset(s) materialized successfully.")
    return 0


@cli.command("install")
@click.option(
    "--manifest",
    "-m",
    "manifest_path",
    default="itqan-assets.yaml",
    show_default=True,
    help="Path to itqan-assets.yaml manifest.",
)
@click.option(
    "--lockfile",
    "-l",
    "lockfile_path",
    default="itqan-assets.lock",
    show_default=True,
    help="Path to itqan-assets.lock lockfile.",
)
@click.option(
    "--assets-dir",
    "-d",
    "assets_dir",
    default=None,
    help="Target directory for downloaded assets. Overrides the manifest's assets_dir "
    f"(default: '{DEFAULT_ASSETS_DIR}' next to the manifest).",
)
@click.option(
    "--registry-url",
    envvar="ITQAN_REGISTRY_URL",
    default=DEFAULT_REGISTRY_URL,
    show_default=True,
    help="URL of the Itqan Package Registry API.",
)
@click.option(
    "--api-key",
    envvar="ITQAN_API_KEY",
    default=None,
    help="API key for authentication & metrics attribution.",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    default=False,
    help="Force re-resolution and re-download of assets.",
)
def install_command(
    manifest_path: str,
    lockfile_path: str,
    assets_dir: str | None,
    registry_url: str,
    api_key: str | None,
    force: bool,
) -> None:
    """Install assets declared in itqan-assets.yaml."""
    api_key = _api_key(api_key, registry_url)
    try:
        exit_code = _run_install(
            manifest_path=manifest_path,
            lockfile_path=lockfile_path,
            assets_dir=assets_dir,
            registry_url=registry_url,
            api_key=api_key,
            force=force,
        )
        sys.exit(exit_code)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        if isinstance(exc, RegistryApiError) and exc.status_code in (401, 403):
            _explain_access(Path(manifest_path), registry_url, api_key)
        sys.exit(exc.exit_code)
    except Exception as exc:
        click.echo(f"Unexpected error: {exc}", err=True)
        sys.exit(1)


def _api_key(api_key: str | None, registry_url: str) -> str | None:
    """--api-key / ITQAN_API_KEY when given, else the key `itqan login` saved for this registry."""
    if api_key:
        return api_key
    try:
        return credentials.load_api_key(registry_url)
    except ItqanCliError as exc:
        click.echo(f"Warning: {exc.message}", err=True)
        return None


def _explain_access(m_path: Path, registry_url: str, api_key: str | None) -> None:
    """After a 401/403, name the manifest's assets the caller can't install
    and where to request access. Best effort: stays quiet if it can't tell."""
    try:
        manifest = load_manifest(m_path)
        catalog = {p.slug: p for p in RegistryClient(base_url=registry_url, api_key=api_key).list_all_packages()}
    except ItqanCliError:
        return
    declared = {entry.asset or entry.slug for entry in manifest.assets.values()}
    for line in browse.access_footer([catalog[slug] for slug in sorted(declared) if slug in catalog], bool(api_key)):
        click.echo(line, err=True)


# Alias: `itqan sync` runs `install`
cli.add_command(install_command, name="sync")


@cli.command("init")
@click.option(
    "--manifest",
    "-m",
    "manifest_path",
    default="itqan-assets.yaml",
    show_default=True,
    help="Path of the manifest to create.",
)
@click.option(
    "--assets-dir",
    "-d",
    "assets_dir",
    default=DEFAULT_ASSETS_DIR,
    show_default=True,
    help="Folder, relative to the manifest, that `itqan install` downloads into.",
)
@click.option(
    "--registry-url",
    envvar="ITQAN_REGISTRY_URL",
    default=DEFAULT_REGISTRY_URL,
    show_default=True,
    help="URL of the Itqan Package Registry API.",
)
@click.option(
    "--api-key",
    envvar="ITQAN_API_KEY",
    default=None,
    help="API key; without one, only open-access assets are suggested.",
)
@click.option("--force", "-f", is_flag=True, default=False, help="Overwrite an existing manifest.")
def init_command(manifest_path: str, assets_dir: str, registry_url: str, api_key: str | None, force: bool) -> None:
    """Create itqan-assets.yaml with a few real assets from the registry.

    If the registry can't be reached, writes the same file with commented-out
    example entries instead.
    """
    m_path = Path(manifest_path)
    if m_path.exists() and not force:
        click.echo(f"Error: {m_path} already exists. Use --force to overwrite it.", err=True)
        sys.exit(1)

    api_key = _api_key(api_key, registry_url)
    try:
        validate_assets_dir(assets_dir)
        client = RegistryClient(base_url=registry_url, api_key=api_key)
        packages = client.list_packages(open_access=None if api_key else True)
        samples = pick_samples([p for p in packages if browse.can_install(p, has_api_key=bool(api_key))])
        if samples:
            content = render_from_catalog(samples, assets_dir)
        else:
            click.echo("Warning: the registry has no installable assets yet; writing commented examples.", err=True)
            content = render_fallback(assets_dir, reason="The registry had no installable assets,")
    except RegistryApiError as exc:
        click.echo(f"Warning: Could not reach the registry ({exc.message}); writing commented examples.", err=True)
        samples = []
        content = render_fallback(assets_dir, reason="Could not reach the registry,")
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)

    parse_manifest_content(content.encode("utf-8"))  # never write a manifest `install` would reject
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(content, encoding="utf-8")
    click.echo(f"Created {m_path} with {len(samples)} sample asset(s).")
    click.echo("Edit it as needed, then run `itqan install` to download the assets.")


@cli.command("browse")
@click.argument("query", required=False)
@click.option("--category", "-c", default=None, help="Only assets of this category (mushaf, tafsir, translation, ...).")
@click.option(
    "--manifest",
    "-m",
    "manifest_path",
    default="itqan-assets.yaml",
    show_default=True,
    help="Manifest to add the picked assets to; created if missing.",
)
@click.option(
    "--lockfile",
    "-l",
    "lockfile_path",
    default="itqan-assets.lock",
    show_default=True,
    help="Lockfile used if you choose to install right away.",
)
@click.option(
    "--interactive/--no-interactive",
    default=None,
    help="Pick assets to add (default when run in a terminal) or just print the list.",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False, help="Print the list as JSON (implies --no-interactive)."
)
@click.option(
    "--registry-url",
    envvar="ITQAN_REGISTRY_URL",
    default=DEFAULT_REGISTRY_URL,
    show_default=True,
    help="URL of the Itqan Package Registry API.",
)
@click.option(
    "--api-key",
    envvar="ITQAN_API_KEY",
    default=None,
    help="API key; without one, assets that need access approval can't be picked.",
)
def browse_command(
    query: str | None,
    category: str | None,
    manifest_path: str,
    lockfile_path: str,
    interactive: bool | None,
    as_json: bool,
    registry_url: str,
    api_key: str | None,
) -> None:
    """Browse installable assets and add them to itqan-assets.yaml.

    QUERY searches names, slugs, descriptions and publishers on the registry;
    without it, every asset is listed and you can filter by typing in the picker.
    """
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if as_json:
        interactive = False
    m_path = Path(manifest_path)
    api_key = _api_key(api_key, registry_url)

    try:
        manifest = load_manifest(m_path) if m_path.exists() else None
        targets = browse.manifest_targets(manifest)
        client = RegistryClient(base_url=registry_url, api_key=api_key)
        packages = client.list_all_packages(search=query, category=category)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)

    if as_json:
        click.echo(json.dumps(browse.to_json(packages, targets), ensure_ascii=False, indent=2))
        return
    if not packages:
        click.echo("No assets match." if query or category else "The registry has no installable assets yet.")
        return
    if not interactive:
        click.echo(browse.render_table(packages, targets))
        if targets:
            click.echo(f"\n* already in {m_path}")
        for line in browse.access_footer(packages, has_api_key=bool(api_key)):
            click.echo(line)
        return

    picked = browse.pick_packages(packages, targets, has_api_key=bool(api_key))
    if not picked:
        click.echo("Nothing added.")
        return
    click.echo(f"Picked: {', '.join(package.slug for package in picked)}")
    picks: list[tuple[CatalogPackage, CatalogLanguage]] = []
    for package in picked:
        languages = browse.pick_languages(package, targets)
        if languages is None:  # Ctrl-C
            click.echo("Nothing added.")
            return
        if len(browse.missing_languages(targets, package)) > 1:
            click.echo(f"  {package.slug}: {', '.join(lang.language or 'source' for lang in languages) or 'none'}")
        picks += [(package, language) for language in languages]

    try:
        added = _add_to_manifest(m_path, manifest, picks)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)
    if not added:
        click.echo("Nothing added.")
        return
    click.echo(f"Added {len(added)} asset(s) to {m_path}: {', '.join(added)}")

    import questionary

    if questionary.confirm("Run `itqan install` now?", default=True).ask():
        install_command.callback(
            manifest_path=str(m_path),
            lockfile_path=lockfile_path,
            assets_dir=None,
            registry_url=registry_url,
            api_key=api_key,
            force=False,
        )
    else:
        click.echo("Run `itqan install` when you're ready to download them.")


def _add_to_manifest(
    m_path: Path, manifest: AssetManifest | None, picks: list[tuple[CatalogPackage, CatalogLanguage]]
) -> list[str]:
    """Write the picked assets into the manifest (creating it if needed) and
    return the new entry names."""
    entries, warnings = browse.plan_entries(picks, manifest)
    for warning in warnings:
        click.echo(f"Warning: {warning}", err=True)
    if not entries:
        return []
    content = m_path.read_text(encoding="utf-8") if manifest is not None else render_header(DEFAULT_ASSETS_DIR)
    updated = browse.add_entries(content, entries)
    m_path.parent.mkdir(parents=True, exist_ok=True)
    m_path.write_text(updated, encoding="utf-8")
    return [entry.name for entry in entries]


# Where users create API keys in the CMS web app.
API_KEYS_PAGE = "https://cms.itqan.dev/account/api-keys"


@cli.command("login")
@click.option(
    "--registry-url",
    envvar="ITQAN_REGISTRY_URL",
    default=DEFAULT_REGISTRY_URL,
    show_default=True,
    help="Registry the key is for.",
)
@click.option("--api-key", default=None, help="The key; prompted for (hidden) when omitted.")
def login_command(registry_url: str, api_key: str | None) -> None:
    """Save your API key so commands can install assets you have approved access to.

    The key is checked against the registry first, then saved for that registry
    in your user config folder, readable only by you. --api-key or ITQAN_API_KEY
    on another command still take precedence over the saved key.
    """
    if not api_key:
        click.echo(f"Create an API key at {API_KEYS_PAGE}")
        api_key = click.prompt("API key", hide_input=True).strip()
    try:
        account = RegistryClient(base_url=registry_url, api_key=api_key).whoami()
    except RegistryApiError as exc:
        if exc.status_code == 401:
            click.echo(f"Error: {registry_url} did not accept that API key. Nothing was saved.", err=True)
            sys.exit(1)
        if exc.status_code != 404:
            click.echo(f"Error: {exc.message}", err=True)
            sys.exit(exc.exit_code)
        account = None  # a registry without the key check: save the key unverified
        click.echo(f"Warning: {registry_url} can't check API keys; saving it unverified.", err=True)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)
    try:
        path = credentials.save_api_key(registry_url, api_key)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)
    if account is None:
        who = ""
    elif account.name and account.name != account.email:
        who = f" as {account.name} <{account.email}>"
    else:
        who = f" as {account.email}"
    click.echo(f"Logged in to {registry_url}{who}. Key saved in {path}.")


@cli.command("logout")
@click.option(
    "--registry-url",
    envvar="ITQAN_REGISTRY_URL",
    default=DEFAULT_REGISTRY_URL,
    show_default=True,
    help="Registry whose saved key to remove.",
)
def logout_command(registry_url: str) -> None:
    """Remove the API key `itqan login` saved for the registry."""
    try:
        removed = credentials.delete_api_key(registry_url)
    except ItqanCliError as exc:
        click.echo(f"Error: {exc.message}", err=True)
        sys.exit(exc.exit_code)
    click.echo(f"Removed the saved key for {registry_url}." if removed else f"No key saved for {registry_url}.")


if __name__ == "__main__":
    cli()

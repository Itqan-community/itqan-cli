"""Package Registry HTTP client for resolving manifests and obtaining download URLs."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from itqan_cli.columns_comment import PackageColumn, PackageStructure
from itqan_cli.exceptions import RegistryApiError
from itqan_cli.usage import usage_headers


@dataclass(frozen=True, slots=True)
class ResolvedAssetPayload:
    slug: str
    asset_version_id: int
    resolved_version: str
    asset_name: str
    download_url: str | None
    publisher_id: int | None = None
    publisher_name: str | None = None
    name: str = ""
    language: str | None = None
    # The publisher went back to an earlier version, withdrawing this one: only an exact
    # (lockfile) pin still gets it. ``withdrawal_reason`` is the reason they gave.
    withdrawn: bool = False
    withdrawal_reason: str | None = None
    # Newer versions the registry knows of: the newest overall, and the newest the
    # manifest's range allows. None from a registry too old to report them.
    latest_version: str | None = None
    latest_in_range: str | None = None
    # Translations / tafsirs: the resolved version's CSV layout. None from other
    # categories and from registries that predate it.
    structure: PackageStructure | None = None

    @property
    def entry_name(self) -> str:
        """The manifest entry this result answers (the slug unless the entry set `asset`)."""
        return self.name or self.slug


@dataclass(frozen=True, slots=True)
class CatalogLanguage:
    language: str
    is_source: bool
    latest_version: str
    # The latest version's CSV layout (translations / tafsirs); None when unknown.
    structure: PackageStructure | None = None


@dataclass(frozen=True, slots=True)
class CatalogPackage:
    """One installable asset from GET /packages/."""

    slug: str
    name: str
    category: str
    is_open_access: bool
    languages: tuple[CatalogLanguage, ...]
    publisher_name: str | None = None
    # The caller's access (open | granted | pending | rejected | none); None from
    # a registry that predates it, which only says whether the asset is open.
    access: str | None = None
    access_request_url: str | None = None


@dataclass(frozen=True, slots=True)
class Account:
    """The owner of an API key, from GET /packages/me/."""

    name: str
    email: str


def parse_structure(raw: object) -> PackageStructure | None:
    """A registry ``structure`` object, or None when it is absent, null or malformed.

    The structure only feeds the column notes written above a manifest entry, so a
    malformed one leaves the notes out rather than failing the whole registry call.
    """
    if not isinstance(raw, dict):
        return None
    template, header, columns = raw.get("template"), raw.get("header"), raw.get("columns")
    if not isinstance(template, str) or not isinstance(header, list) or not isinstance(columns, list):
        return None
    if not all(isinstance(name, str) for name in header):
        return None
    if not all(isinstance(column, dict) and isinstance(column.get("key"), str) for column in columns):
        return None
    return PackageStructure(
        template=template,
        header=tuple(header),
        columns=tuple(
            PackageColumn(
                key=column["key"],
                label_en=_label(column.get("label_en")),
                label_ar=_label(column.get("label_ar")),
            )
            for column in columns
        ),
    )


def _label(raw: object) -> str:
    """A column label, or "" when it is missing or not text."""
    return raw if isinstance(raw, str) else ""


# The public API (not the cms.itqan.dev website, which serves the web app).
DEFAULT_REGISTRY_URL = "https://api.cms.itqan.dev"


def _error_detail(response: requests.Response) -> str:
    """`: <reason>` from an error body like a 400 validation error, or ""."""
    try:
        body = response.json()
        extra = body.get("extra") or []
        reason = extra[0]["msg"] if extra and isinstance(extra[0], dict) else body.get("message")
    except (ValueError, AttributeError, KeyError, TypeError):
        return ""
    return f": {reason}" if reason else ""


class RegistryClient:
    """HTTP Client for Itqan Package Registry API."""

    def __init__(
        self,
        base_url: str = DEFAULT_REGISTRY_URL,
        api_key: str | None = None,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.session = session or requests.Session()

        # Security: reject HTTP for non-loopback URLs when an API key is provided.
        # Sending an API key over plain HTTP exposes it to network eavesdroppers.
        if api_key:
            parsed = __import__("urllib.parse", fromlist=["urlparse"]).urlparse(self.base_url)
            is_loopback = parsed.hostname in ("localhost", "127.0.0.1", "::1")
            if parsed.scheme == "http" and not is_loopback:
                raise RegistryApiError(
                    "Refusing to send API key over an insecure HTTP connection. "
                    "Use HTTPS or a loopback address for development."
                )

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **usage_headers(),
        }
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def list_packages(
        self,
        *,
        open_access: bool | None = None,
        search: str | None = None,
        category: str | None = None,
        page_size: int = 50,
    ) -> list[CatalogPackage]:
        """Call GET /packages/ for the first page of installable assets.

        Raises:
            RegistryApiError when the registry can't be reached or answers badly.
        """
        packages, _ = self._catalog_page(
            open_access=open_access, search=search, category=category, page=1, page_size=page_size
        )
        return packages

    def list_all_packages(
        self,
        *,
        open_access: bool | None = None,
        search: str | None = None,
        category: str | None = None,
        page_size: int = 50,
    ) -> list[CatalogPackage]:
        """Every installable asset matching the filters, following GET /packages/ pagination.

        Raises:
            RegistryApiError when the registry can't be reached or answers badly.
        """
        packages: list[CatalogPackage] = []
        page = 1
        while True:
            batch, count = self._catalog_page(
                open_access=open_access, search=search, category=category, page=page, page_size=page_size
            )
            packages.extend(batch)
            if not batch or len(packages) >= count:
                return packages
            page += 1

    def _catalog_page(
        self,
        *,
        open_access: bool | None,
        search: str | None,
        category: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[CatalogPackage], int]:
        """One page of GET /packages/ and the total number of matching assets."""
        params: dict[str, str] = {"page_size": str(page_size)}
        if page > 1:
            params["page"] = str(page)
        if open_access is not None:
            params["open_access"] = "true" if open_access else "false"
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        try:
            response = self.session.get(
                f"{self.base_url}/packages/", params=params, headers=self._headers(), timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise RegistryApiError(f"Failed to connect to package registry at {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise RegistryApiError(
                f"Registry catalog request failed with status {response.status_code}{_error_detail(response)}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
            packages = [
                CatalogPackage(
                    slug=item["slug"],
                    name=item["name"],
                    category=item["category"],
                    is_open_access=item["is_open_access"],
                    publisher_name=item.get("publisher_name"),
                    access=item.get("access"),
                    access_request_url=item.get("access_request_url"),
                    languages=tuple(
                        CatalogLanguage(
                            language=lang["language"],
                            is_source=lang["is_source"],
                            latest_version=lang["latest_version"],
                            structure=parse_structure(lang.get("structure")),
                        )
                        for lang in item["languages"]
                    ),
                )
                for item in body["results"]
            ]
            return packages, int(body.get("count", len(packages)))
        except (ValueError, KeyError, TypeError) as exc:
            raise RegistryApiError(f"Failed to parse registry catalog response: {exc}") from exc

    def whoami(self) -> Account:
        """Call GET /packages/me/ to check the API key.

        Raises:
            RegistryApiError with status_code 401 when the key is missing or
                invalid, 404 when the registry has no such endpoint.
        """
        try:
            response = self.session.get(f"{self.base_url}/packages/me/", headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            raise RegistryApiError(f"Failed to connect to package registry at {self.base_url}: {exc}") from exc
        if response.status_code != 200:
            raise RegistryApiError(
                f"API key check failed with status {response.status_code}{_error_detail(response)}",
                status_code=response.status_code,
            )
        try:
            body = response.json()
            return Account(name=body["name"], email=body["email"])
        except (ValueError, KeyError, TypeError) as exc:
            raise RegistryApiError(f"Failed to parse API key check response: {exc}") from exc

    def resolve_manifest(self, assets: dict[str, str | dict[str, str]]) -> list[ResolvedAssetPayload]:
        """Call POST /packages/resolve/manifest/ to resolve manifest constraints.

        Args:
            assets: dict of entry name -> constraint string (e.g. {"quran": "^2.1.0"}),
                or -> request object ({"version": ..., "asset": ..., "language": ...})

        Returns:
            list of ResolvedAssetPayload

        Raises:
            RegistryApiError on any failure.
        """
        url = f"{self.base_url}/packages/resolve/manifest/"
        payload = {"assets": assets}

        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise RegistryApiError(f"Failed to connect to package registry at {self.base_url}: {exc}") from exc

        if response.status_code == 200:
            try:
                data = response.json()
                # Require "results" to be explicitly present as a list.
                # A missing key means the response is malformed — do not silently
                # continue with zero assets, as that would allow _run_install to
                # report success while writing an empty lockfile.
                if "results" not in data or not isinstance(data["results"], list):
                    raise RegistryApiError(
                        "Registry returned a 200 response but 'results' field is missing or not a list. "
                        "Cannot proceed with installation."
                    )
                results_raw = data["results"]
                requested_slugs = set(assets.keys())
                returned_slugs = {item.get("name") or item["slug"] for item in results_raw if isinstance(item, dict)}
                missing = requested_slugs - returned_slugs
                if missing:
                    raise RegistryApiError(
                        f"Registry resolved {len(returned_slugs)} of {len(requested_slugs)} requested assets. "
                        f"Missing: {', '.join(sorted(missing))}"
                    )
                return [
                    ResolvedAssetPayload(
                        slug=item["slug"],
                        asset_version_id=item["asset_version_id"],
                        resolved_version=item["resolved_version"],
                        asset_name=item["asset_name"],
                        download_url=item.get("download_url"),
                        publisher_id=item.get("publisher_id"),
                        publisher_name=item.get("publisher_name"),
                        name=item.get("name") or item["slug"],
                        language=item.get("language"),
                        withdrawn=bool(item.get("withdrawn", False)),
                        withdrawal_reason=item.get("withdrawal_reason"),
                        latest_version=item.get("latest_version"),
                        latest_in_range=item.get("latest_in_range"),
                        structure=parse_structure(item.get("structure")),
                    )
                    for item in results_raw
                ]
            except RegistryApiError:
                raise
            except Exception as exc:
                raise RegistryApiError(f"Failed to parse registry API response: {exc}") from exc

        # Handle API Error responses
        status_code = response.status_code
        error_name: str | None = None
        message = f"Registry request failed with status {status_code}"

        try:
            err_data = response.json()
            if isinstance(err_data, dict):
                error_name = err_data.get("error_name") or err_data.get("error")
                message = err_data.get("message") or err_data.get("detail") or message
        except Exception:
            message = response.text or message

        if status_code == 401:
            friendly_msg = f"Authentication required (API key missing or invalid): {message}"
        elif status_code == 403:
            friendly_msg = f"Access denied for requested assets (approved access required): {message}"
        elif status_code == 404:
            friendly_msg = f"Asset or version not found in registry: {message}"
        elif status_code == 410:
            friendly_msg = (
                f"Version removed from the registry: {message} "
                "Run `itqan install --force` to resolve another version, or change it in your manifest."
            )
        elif status_code == 422:
            friendly_msg = f"Cannot satisfy version constraints: {message}"
        else:
            friendly_msg = f"Registry API error [{status_code}]: {message}"

        raise RegistryApiError(
            friendly_msg,
            status_code=status_code,
            error_name=error_name,
        )

# itqan-cli

**Itqan Quranic Asset Manager**

Install and pin [Itqan](https://cms.itqan.dev) Quranic assets (mushafs, tafsirs, translations,
recitations, fonts) in your project, the way a package manager does for code.

You declare the assets you use and the versions you accept in `itqan-assets.yaml`. The CLI
resolves them against the Itqan registry, downloads them, and records the exact versions in
`itqan-assets.lock`, so teammates and CI get the same files.

## Install

Requires Python 3.11+.

```bash
pipx install itqan-cli        # or: uv tool install itqan-cli
```

## Quick start

```bash
itqan init        # writes itqan-assets.yaml with a few real assets as examples
itqan install     # downloads them and writes itqan-assets.lock
```

Commit both `itqan-assets.yaml` and `itqan-assets.lock`. The downloaded files are reproducible
from the lockfile, so add the assets folder to `.gitignore` if you like.

## The manifest

```yaml
schema_version: 1

# Folder the assets are downloaded into, relative to this file (default: assets).
assets_dir: "public/quran"

assets:
  # Source language of the asset.
  tafsir-jalalayn:
    version: "^2.0.0"     # any 2.x from 2.0.0 on

  # The same asset in English: its own entry, pointing at the asset.
  tafsir-jalalayn-en:
    asset: tafsir-jalalayn
    language: en
    version: "~1.3"       # any 1.3.x
```

Each language of an asset has its own version history, so each gets its own entry, constraint,
lock entry and folder (`public/quran/tafsir-jalalayn-en/`). The full format is specified in
[ASSET_MANIFEST.md](https://github.com/Itqan-community/cms-backend/blob/main/docs/ASSET_MANIFEST.md).

## Commands

| Command | What it does |
|---|---|
| `itqan init` | Create `itqan-assets.yaml` from the registry's catalog (commented examples when offline). `--assets-dir`, `--force`. |
| `itqan install` | Resolve, download and lock. Uses the lockfile's exact versions when it is up to date; `--force` re-resolves. |
| `itqan sync` | Same as `install`. |
| `itqan --version` | Print the CLI version. |

## Configuration

| Option | Environment variable | Default |
|---|---|---|
| `--registry-url` | `ITQAN_REGISTRY_URL` | `https://cms.itqan.dev` |
| `--api-key` | `ITQAN_API_KEY` | none; needed only for assets that require access approval |

## Development

```bash
uv sync
uv run pytest
uv build
```

Releases are published from version tags; see [RELEASING.md](RELEASING.md).

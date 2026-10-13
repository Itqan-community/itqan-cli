# itqan-cli

[![CI](https://github.com/Itqan-community/itqan-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Itqan-community/itqan-cli/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/Itqan-community/itqan-cli)](https://github.com/Itqan-community/itqan-cli/releases/latest)
[![PyPI](https://img.shields.io/pypi/v/itqan-cli)](https://pypi.org/project/itqan-cli/)
[![Python](https://img.shields.io/pypi/pyversions/itqan-cli)](https://pypi.org/project/itqan-cli/)
[![npm](https://img.shields.io/npm/v/itqan-cli)](https://www.npmjs.com/package/itqan-cli)
[![pub.dev](https://img.shields.io/pub/v/itqan_cli)](https://pub.dev/packages/itqan_cli)
[![Homebrew](https://img.shields.io/badge/homebrew-itqan--community%2Ftap-orange)](https://github.com/Itqan-community/homebrew-tap)
[![GitHub Action](https://img.shields.io/github/v/release/Itqan-community/setup-itqan?label=setup-itqan)](https://github.com/Itqan-community/setup-itqan)
[![npm downloads](https://img.shields.io/npm/dm/itqan-cli?label=npm%20downloads)](https://www.npmjs.com/package/itqan-cli)
[![PyPI downloads](https://img.shields.io/pypi/dm/itqan-cli?label=PyPI%20downloads)](https://pypi.org/project/itqan-cli/)
[![License: MIT](https://img.shields.io/github/license/Itqan-community/itqan-cli)](LICENSE)

**Itqan Quranic Asset Manager**

`itqan` adds [Itqan](https://cms.itqan.dev) Quranic data, such as mushafs, tafsirs,
translations and fonts, to your app's project, the way npm or pub adds code libraries.

1. You list the assets you want, and which versions you accept, in `itqan-assets.yaml`.
2. `itqan install` downloads them into a folder in your project.
3. It records the exact versions it installed in `itqan-assets.lock`, so your teammates and your
   CI get exactly the same files.

It works for any kind of project (web, React Native, Flutter, Python or anything else) on macOS,
Linux and Windows.

**Contents:** [Install](#install) · [Quick start](#quick-start) ·
[Use the assets in your app](#use-the-assets-in-your-app) · [The manifest](#the-manifest) ·
[Updating assets](#updating-assets) · [Assets that need access approval](#assets-that-need-access-approval) ·
[CI](#ci) · [Commands](#commands) · [Configuration](#configuration) ·
[Troubleshooting](#troubleshooting)

## Install

Pick the line for the tools you already have. Each one gives you the same `itqan` command.

| You work with | Install | Needs Python? |
|---|---|---|
| JavaScript, TypeScript, React Native | `npm install --save-dev itqan-cli` (or just `npx itqan-cli ...`) | No |
| Dart or Flutter | `dart pub global activate itqan_cli` | No |
| macOS or Linux, with Homebrew | `brew install itqan-community/tap/itqan` | No |
| Python 3.11 or newer | `pipx install itqan-cli` or `uv tool install itqan-cli` | Yes |
| GitHub Actions | `uses: itqan-community/setup-itqan@v1` (see [CI](#ci)) | No |
| None of these | [Download the program](#download-the-program-directly) | No |

Check that it works:

```bash
itqan --version
```

The options that don't need Python run a ready-made `itqan` program for your computer. It exists
for macOS (Apple Silicon and Intel), Linux (x86_64 and arm64, with glibc) and Windows (x86_64).
On any other system, such as Windows on ARM or Alpine Linux, install with Python.

### npm

Add it to your project, so everyone on the team gets the same version:

```bash
npm install --save-dev itqan-cli
```

Then run it with `npx itqan ...`, or from a script in `package.json`:

```json
{
  "scripts": {
    "assets": "itqan install"
  }
}
```

To try it without installing anything, use `npx itqan-cli init` and `npx itqan-cli install`.

### Dart and Flutter

```bash
dart pub global activate itqan_cli
```

If `itqan` isn't found afterwards, add pub's folder to your `PATH`. `dart pub global activate`
prints the folder to add.

The package version is the CLI version: `dart pub global activate itqan_cli 0.2.0` gives you
itqan 0.2.0. The first time you run `itqan`, it downloads the program for your computer from the
[GitHub Release](https://github.com/Itqan-community/itqan-cli/releases), checks it against the
release's `SHA256SUMS` file, and keeps it for later runs.

### Homebrew

```bash
brew install itqan-community/tap/itqan
brew upgrade itqan    # later, to update
```

### Python

```bash
pipx install itqan-cli        # or: uv tool install itqan-cli
```

This installs `itqan`, and the same command again under the name `itqan-cli`.

### Download the program directly

Each [GitHub Release](https://github.com/Itqan-community/itqan-cli/releases) has the program for
each system, named `itqan-<version>-<os>-<arch>` (with `.exe` on Windows), and a `SHA256SUMS`
file to check it with. Download yours, check it, and put it on your `PATH` as `itqan`. On an Apple
Silicon Mac, for example:

```bash
v=0.2.0   # the release you want
curl -fLO "https://github.com/Itqan-community/itqan-cli/releases/download/v$v/itqan-$v-macos-arm64"
curl -fLO "https://github.com/Itqan-community/itqan-cli/releases/download/v$v/SHA256SUMS"
shasum -a 256 --check --ignore-missing SHA256SUMS     # Linux: sha256sum --check --ignore-missing SHA256SUMS
chmod +x "itqan-$v-macos-arm64"
sudo mv "itqan-$v-macos-arm64" /usr/local/bin/itqan
```

On Windows, download `itqan-<version>-windows-x86_64.exe`, rename it to `itqan.exe`, and put it in
a folder on your `PATH`.

## Quick start

Run these in your project's folder:

```bash
itqan init        # 1. create itqan-assets.yaml, with commented-out example assets
itqan browse      # 2. search the catalog and add the assets you want (or uncomment the examples)
itqan install     # 3. download them and write itqan-assets.lock
```

You now have:

```
your-project/
├── itqan-assets.yaml     # what you asked for: edit this, and commit it
├── itqan-assets.lock     # what was installed: don't edit it, but commit it
└── assets/
    ├── english-translation/
    │   └── tr-ab-en_hilali.csv
    ├── tafsir-jalalayn/
    │   └── ...
    └── .itqan/           # the CLI's own bookkeeping, not part of any asset
```

Commit `itqan-assets.yaml` and `itqan-assets.lock`. You can commit the `assets/` folder too, or
add it to `.gitignore` and run `itqan install` after cloning (and in CI), which downloads exactly
the versions in the lockfile.

In `itqan browse`, type to filter the list, press Enter to add the highlighted asset, or press
Space on several and then Enter. `itqan browse tafsir` starts with a search, and
`itqan browse --category translation` shows one kind of asset.

## Use the assets in your app

Each asset goes into its own folder, `<assets_dir>/<entry name>/`. `assets_dir` is `assets` unless
your manifest says otherwise (see [The manifest](#the-manifest)). Point it at the folder your
framework already serves or bundles.

### Web apps (Vite, Next.js, Create React App, and others)

Install into the `public/` folder, which these tools serve as-is:

```yaml
# itqan-assets.yaml
assets_dir: "public/quran"
```

The files are then served from `/quran/`:

```js
const csv = await fetch("/quran/english-translation/tr-ab-en_hilali.csv").then((r) => r.text());
```

### Flutter

Flutter only bundles the folders listed in `pubspec.yaml`, and listing a folder doesn't include
its subfolders. `itqan` can keep that list for you. Put `itqan-assets.yaml` next to
`pubspec.yaml`, and install once with `--flutter`:

```bash
itqan install --flutter
```

This adds every folder with installed files to `flutter: assets:`, inside a block that `itqan`
manages:

```yaml
flutter:
  assets:
    - images/            # your own entries are left alone
    # itqan:start (managed by `itqan install`, do not edit)
    - assets/english-translation/
    - assets/tafsir-jalalayn/
    # itqan:end
```

Commit `pubspec.yaml` with the block. From then on, every `itqan install` (yours, a teammate's,
CI's) keeps the block in step with the manifest, with no flag needed. Nothing else in
`pubspec.yaml` is changed, and the file isn't touched at all when nothing changed. Load the files
with `rootBundle`:

```dart
import 'package:flutter/services.dart';

final csv = await rootBundle.loadString('assets/english-translation/tr-ab-en_hilali.csv');
```

To stop, delete the block, including both marker lines. To skip it for one run, pass
`--no-flutter`.

### React Native, Python and everything else

The assets are plain files in `<assets_dir>/<entry name>/`. Read them, bundle them or copy them
the way your platform handles any other data file.

## The manifest

`itqan-assets.yaml` lists the assets you want. `itqan init` writes one for you, with comments
explaining each part and a few real assets from the catalog as commented-out examples, one of
them with a `language:`. A fuller example:

```yaml
schema_version: 1

# Where to download the assets, relative to this file. Optional, defaults to "assets".
assets_dir: "public/quran"

assets:
  # The entry's name is the asset's name in the catalog (as `itqan browse` shows it).
  tafsir-jalalayn:
    version: "^2.0.0"

  # The same asset in English. Each language is its own entry with its own folder, so it needs its
  # own name and has to say which asset it is.
  tafsir-jalalayn-en:
    asset: tafsir-jalalayn
    language: en
    version: "~1.3"
```

Which versions an entry accepts:

| `version:` | Accepts | Example |
|---|---|---|
| `"^2.1.0"` | any newer version that keeps the same first number | 2.1.0, 2.4.3, not 3.0.0 |
| `"~2.1"` | only fixes to 2.1 | 2.1.0, 2.1.7, not 2.2.0 |
| `"2.1.0"` | exactly this version | 2.1.0 only |

Use `^` unless you have a reason not to. A publisher changes the first number when an update
could break apps that use the asset. Below 1.0 the second number plays that role, so `"^0.3.0"`
accepts 0.3.x only.

Each language of an asset has its own version history. That's why `tafsir-jalalayn` above is on
2.x while its English translation is on 1.3.x. Leave out `language` to get the asset's original
language.

The full format, including every rule and error, is specified in
[ASSET_MANIFEST.md](https://github.com/Itqan-community/cms-backend/blob/main/docs/ASSET_MANIFEST.md).

## Updating assets

- **Add or remove an asset, or change a `version:` range:** edit `itqan-assets.yaml` and run
  `itqan install`. It sees that the lockfile no longer matches the manifest, picks the newest
  versions the manifest allows, and rewrites the lockfile.
- **Get newer versions within the ranges you already have:** `itqan install --force`.
- **Install what the lockfile says, for example after cloning or in CI:** `itqan install`.

`itqan install` writes the lockfile only after every download succeeded, so a failed install
never leaves a lockfile that doesn't match your files.

## Assets that need access approval

Some publishers approve each developer before their assets can be downloaded.

1. `itqan browse` lists these assets too, marked `request access`, `access pending` or
   `access rejected`, with a link to the asset's page on cms.itqan.dev. Request access there.
2. Once you're approved, create an API key at
   [cms.itqan.dev/account/api-keys](https://cms.itqan.dev/account/api-keys) and save it:

   ```bash
   itqan login
   ```

3. The asset now shows as `granted` in `itqan browse`, and `itqan install` can download it.

If `itqan install` hits an asset you can't download yet, it says which one and where to request
access. In CI, pass the key in the `ITQAN_API_KEY` environment variable instead of
`itqan login`.

## CI

Run `itqan install` in CI to download the exact versions in `itqan-assets.lock`. On a pull
request that updates an asset, this also checks that the new version installs.

### GitHub Actions

The [setup-itqan](https://github.com/Itqan-community/setup-itqan) action installs `itqan` on
Linux, macOS and Windows runners:

```yaml
steps:
  - uses: actions/checkout@v7
  - uses: itqan-community/setup-itqan@v1
    with:
      version: latest       # or a fixed version, such as 0.2.0
  - run: itqan install
    env:
      ITQAN_API_KEY: ${{ secrets.ITQAN_API_KEY }}   # only needed for assets that need access approval
```

Pass `install: true` to have the action run `itqan install` itself. The
[action's README](https://github.com/Itqan-community/setup-itqan#readme) lists all its options.

### Get a pull request when assets have new versions

Dependabot and similar tools don't read `itqan-assets.yaml`. To get the same kind of pull request,
add a workflow that runs `itqan install --force` on a schedule. It picks the newest versions your
manifest allows, and when that changes the lockfile, it opens a pull request (or updates the open
one):

```yaml
# .github/workflows/update-itqan-assets.yml
name: Update Itqan assets

on:
  schedule:
    - cron: "0 6 * * 1"   # every Monday at 06:00 UTC
  workflow_dispatch:      # and whenever you run it by hand

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: itqan-community/setup-itqan@v1
      - run: itqan install --force
        env:
          ITQAN_API_KEY: ${{ secrets.ITQAN_API_KEY }}   # only needed for assets that need access approval
      - uses: peter-evans/create-pull-request@v8
        with:
          branch: itqan/update-assets
          commit-message: "chore: update Itqan assets"
          title: "Update Itqan assets"
          body: "`itqan install --force` found newer versions allowed by `itqan-assets.yaml`."
```

The pull request includes `itqan-assets.lock`, and the asset files too if you commit them. Add
`--flutter` to the install if you use [Flutter](#flutter), so `pubspec.yaml` stays in step.

Two GitHub settings to know about:

- Turn on **Settings > Actions > General > Allow GitHub Actions to create and approve pull
  requests**, or the last step fails.
- Pull requests opened with the default `GITHUB_TOKEN` don't start your other workflows, so CI
  won't run on them by itself. To have it run, give the step a `token:` from a GitHub App or a
  personal access token, or close and reopen the pull request.

It only moves within the ranges in your manifest. To go to a new major version, change the
`version:` range yourself.

### Other CI systems

Install `itqan` with whichever method from [Install](#install) suits your build image. For
example, `npm ci` for a project with `itqan-cli` in its `devDependencies`, or
`pipx install itqan-cli`. Then run `itqan install`, with `ITQAN_API_KEY` set if you need it.

## Commands

| Command | What it does |
|---|---|
| `itqan init` | Create `itqan-assets.yaml` with a few assets from the catalog as commented-out examples (placeholder examples when offline). `--assets-dir` sets where assets go; `--force` overwrites an existing manifest. |
| `itqan browse [SEARCH]` | Search the catalog, pick assets, add them to `itqan-assets.yaml` (created if missing), and optionally install them. `--category` limits it to one kind of asset; `--no-interactive` prints a table (the default when not in a terminal); `--json` prints JSON. |
| `itqan install` | Download the assets and write `itqan-assets.lock`. Uses the lockfile's exact versions while it matches the manifest. `--force` picks the newest allowed versions and downloads again. `--flutter` keeps `pubspec.yaml` up to date (see [Flutter](#flutter)). `--assets-dir` overrides the manifest's folder for one run. |
| `itqan sync` | Same as `itqan install`. |
| `itqan login` | Save your API key for the registry, after checking it. `--api-key` passes the key without the prompt. |
| `itqan logout` | Remove the saved key. |
| `itqan --version` | Print the CLI version. |

Add `--help` to any command for all its options. `install` and `browse` read the manifest from
`itqan-assets.yaml` in the current folder; `--manifest` (or `-m`) points them elsewhere.

## Configuration

| Option | Environment variable | Default |
|---|---|---|
| `--api-key` | `ITQAN_API_KEY` | The key saved by `itqan login`, if any. |
| `--registry-url` | `ITQAN_REGISTRY_URL` | `https://api.cms.itqan.dev`, the public registry. |
| | `ITQAN_CONFIG_DIR` | Where `itqan login` saves keys: `~/.config/itqan` (`%APPDATA%\itqan` on Windows). |
| | `ITQAN_CACHE_DIR` | Dart package only. Where the downloaded program is kept: `~/Library/Caches/itqan` (macOS), `~/.cache/itqan` (Linux), `%LOCALAPPDATA%\itqan` (Windows). |
| | `ITQAN_CLI_DOWNLOAD_URL` | Dart package only. A folder (`https://` or `file://`) with a release's programs and `SHA256SUMS`, such as a mirror, used instead of the GitHub Release. |

A key passed with `--api-key` or `ITQAN_API_KEY` is used instead of the saved one. The saved key
file is readable only by you.

## Troubleshooting

**"command not found: itqan".** The folder `itqan` was installed into isn't on your `PATH`. For
pipx, run `pipx ensurepath`. For Dart, add the folder `dart pub global activate` printed. For npm,
run it through `npx itqan`.

**macOS says the program can't be opened.** Programs downloaded with a browser are blocked
because they aren't notarized by Apple. Allow it with
`xattr -d com.apple.quarantine /usr/local/bin/itqan`. Downloads made with `curl`, Homebrew, npm
or Dart aren't affected.

**npm: "@itqan-community/cli-... is not installed".** npm installs the program for your computer
as an optional dependency of `itqan-cli`. Reinstall without `--omit=optional` or
`--no-optional`.

**"There is no itqan binary for ..." or "no prebuilt binary".** Your system isn't one of those
listed under [Install](#install). Install with Python instead: `pipx install itqan-cli`.

**`itqan install` says an asset needs access, or returns 401 or 403.** See
[Assets that need access approval](#assets-that-need-access-approval). In CI, check that
`ITQAN_API_KEY` is set.

**"Warning: ... was withdrawn by its publisher".** Your lockfile pins a version the publisher
has since withdrawn by going back to an earlier version, usually because of a mistake in it; the
warning shows the reason they gave. It still installs, so your build
keeps working, but new installs no longer get it. Run `itqan install --force` to move to the
newest supported version in your range, or change the version in `itqan-assets.yaml` if you
pinned it there.

**"Version removed from the registry" (410).** Itqan removed that version, for example because
its licence was revoked, and it can't be downloaded any more. Run `itqan install --force` to
resolve another version, or change the version in `itqan-assets.yaml`.

**Flutter: "Unable to load asset".** Make sure the manifest sits next to `pubspec.yaml`, run
`itqan install --flutter`, and then restart the app fully. Hot reload doesn't pick up new assets.

## Development

```bash
uv sync
uv run pytest
uv build
uv run --group binary pyinstaller --onefile --name itqan --copy-metadata itqan-cli --specpath build src/itqan_cli/__main__.py  # dist/itqan
```

The npm package is built from [npm/](npm) and the pub.dev package lives in [dart/](dart) (tested
with `dart test`). Releases are published from version tags; see [RELEASING.md](RELEASING.md).

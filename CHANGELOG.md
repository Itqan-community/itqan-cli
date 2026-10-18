## v0.3.0 (2026-10-18)

### Feat

- `itqan add ASSET[@RANGE]...` adds assets to `itqan-assets.yaml` (creating it if missing) and
  installs them. Without a range it accepts the newest version (`^`); `--language` picks another
  language and `--no-install` only edits the manifest. Unknown assets, assets you don't have access
  to and unavailable languages fail before anything is written.
- `itqan install` says when your locked assets have newer versions, split into those your range
  allows (`itqan install --force`) and those it doesn't. `ITQAN_NO_UPDATE_NOTICE=1` turns it off.
  The new `itqan outdated` command lists them, or prints them as JSON with `--json`.
- warn when a locked version was withdrawn by its publisher: `itqan install` still installs it and
  shows the publisher's reason and how to move off it. A version removed by an Itqan admin fails
  with an explanation and suggests `itqan install --force`.
- **init**: `itqan init` writes the example assets commented out instead of installing them right
  away, and suggests `itqan browse` to find assets.

### Fix

- **cli**: `itqan --help` shows each command's full description instead of cutting it off with
  `...`.

## v0.2.0 (2026-10-12)

### Feat

- publish to pub.dev as `itqan_cli`: `dart pub global activate itqan_cli` installs `itqan` without
  Python. It downloads the program for your computer on first use, checks it against the
  release's `SHA256SUMS`, and keeps it for later runs.
- **flutter**: `itqan install --flutter` lists the installed asset folders under `flutter: assets:`
  in `pubspec.yaml`, inside an `# itqan:start` / `# itqan:end` block. Later installs keep the block
  in sync without the flag, and the rest of the file is never changed.
- **ci**: the [setup-itqan](https://github.com/Itqan-community/setup-itqan) GitHub Action installs
  `itqan` on Linux, macOS and Windows runners: `uses: itqan-community/setup-itqan@v1`.

### Fix

- keep version markers out of the asset folders, where Flutter bundled them into apps. They now
  live in `<assets_dir>/.itqan/`. Existing installs are moved over on the next `itqan install`
  without downloading again.

### Docs

- rewrite the README around what you want to do: pick an install method for your project, get
  started, use the assets in a web or Flutter app, update them, and set up CI.

## v0.1.3 (2026-10-11)

### Fix

- **release**: publish npm tarballs by ./ path

## v0.1.2 (2026-10-11)

### Feat

- publish to npm as itqan-cli

## v0.1.1 (2026-10-11)

### Feat

- publish a Homebrew formula on each release

### Fix

- **browse**: say when an asset has no published version yet

## v0.1.0 (2026-10-11)

### Feat

- attach standalone binaries to each GitHub Release
- show which gated assets need access and where to request it
- add `itqan login` / `logout` to save an API key
- also install the CLI as `itqan-cli`
- add `itqan browse` to search the catalog and add assets

### Fix

- **browse**: Enter adds the highlighted asset when none is selected
- **browse**: fit picker rows to the terminal and summarize the picks

## v0.1.0rc1 (2026-10-08)

### Feat

- **package-manager**: add `itqan init` to create a starter manifest
- **package-manager**: let the manifest choose the assets folder
- **package-manager**: resolve per language and generate missing files on download
- **package-manager**: add itqan install CLI (ITQ-22) (#503)

### Fix

- default to the public API host, api.cms.itqan.dev
- report the real CLI version in the User-Agent
- **package-manager**: default the CLI to the production registry

### Refactor

- **package-manager**: move the itqan CLI into a standalone package

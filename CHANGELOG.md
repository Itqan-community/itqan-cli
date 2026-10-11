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

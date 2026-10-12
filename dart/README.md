# itqan_cli

Install and pin [Itqan](https://cms.itqan.dev) Quranic assets (mushafs, tafsirs, translations,
fonts) in your Dart or Flutter project, the way a package manager does for code.

```bash
dart pub global activate itqan_cli
itqan init        # create itqan-assets.yaml
itqan install     # download the assets it declares and write itqan-assets.lock
```

In a Flutter app, run `itqan install --flutter` to also list the installed asset folders in
`pubspec.yaml`, so Flutter bundles them.

The package version is the version of the CLI it runs: `dart pub global activate itqan_cli 0.2.0`
runs itqan 0.2.0. On first use it downloads the standalone `itqan` binary for your machine
(macOS arm64/x64, Linux arm64/x64 with glibc, Windows x64) from the
[GitHub Release](https://github.com/Itqan-community/itqan-cli/releases), checks it against the
release's `SHA256SUMS`, and keeps it in your cache folder. Python isn't needed.

| Variable | Use |
|---|---|
| `ITQAN_CACHE_DIR` | Where to keep downloaded binaries, instead of `~/Library/Caches/itqan` (macOS), `$XDG_CACHE_HOME/itqan` or `~/.cache/itqan` (Linux), `%LOCALAPPDATA%\itqan` (Windows). |
| `ITQAN_CLI_DOWNLOAD_URL` | A folder (`https://` or `file://`) holding the release's binaries and `SHA256SUMS`, such as a mirror, instead of the GitHub Release. |

See the [itqan-cli README](https://github.com/Itqan-community/itqan-cli#readme) for the commands
and the manifest format.

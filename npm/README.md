# itqan-cli

Install and pin [Itqan](https://github.com/Itqan-community) Quranic assets in your project.

```bash
npx itqan-cli init       # create itqan-assets.yaml
npx itqan-cli install    # download the assets it declares
```

Or add it to your project and call `itqan` from `package.json` scripts:

```bash
npm install --save-dev itqan-cli
```

```json
{
  "scripts": {
    "assets": "itqan install"
  }
}
```

This package runs the standalone `itqan` binary for your platform (macOS arm64/x64, Linux
arm64/x64 with glibc, Windows x64), so Python isn't needed. See the
[itqan-cli README](https://github.com/Itqan-community/itqan-cli#readme) for the commands and the
manifest format.

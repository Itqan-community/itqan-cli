#!/usr/bin/env node
"use strict";

// The `itqan` command of the itqan-cli npm package. npm installs only the platform package that
// matches this machine (an optional dependency limited by `os`/`cpu`); this runs its standalone
// binary. Packages are built by scripts/npm_packages.py.

const { spawnSync } = require("node:child_process");

const PACKAGES = {
  "darwin-arm64": "@itqan-community/cli-darwin-arm64",
  "darwin-x64": "@itqan-community/cli-darwin-x64",
  "linux-arm64": "@itqan-community/cli-linux-arm64",
  "linux-x64": "@itqan-community/cli-linux-x64",
  "win32-x64": "@itqan-community/cli-win32-x64",
};

const platform = `${process.platform}-${process.arch}`;
const pkg = PACKAGES[platform];
if (!pkg) {
  console.error(`itqan: no prebuilt binary for ${platform}. Install with Python instead: pipx install itqan-cli`);
  process.exit(1);
}

let binary;
try {
  binary = require.resolve(`${pkg}/bin/itqan${process.platform === "win32" ? ".exe" : ""}`);
} catch {
  console.error(
    `itqan: ${pkg} is not installed. It's an optional dependency of itqan-cli, so reinstall ` +
      "without --omit=optional (or --no-optional).",
  );
  process.exit(1);
}

const result = spawnSync(binary, process.argv.slice(2), { stdio: "inherit" });
if (result.error) {
  console.error(`itqan: could not run ${binary}: ${result.error.message}`);
  process.exit(1);
}
if (result.signal) {
  process.kill(process.pid, result.signal);
}
process.exit(result.status ?? 1);

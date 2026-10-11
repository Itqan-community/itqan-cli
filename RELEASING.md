# Releasing

Releases are published by [`.github/workflows/release.yml`](.github/workflows/release.yml) when a
version tag is pushed. It runs the tests, builds the package and the standalone binaries
([`binaries.yml`](.github/workflows/binaries.yml)), publishes the package to
[PyPI](https://pypi.org/project/itqan-cli/) and creates the GitHub Release with the package, the
binaries and a `SHA256SUMS` file. Nothing is published unless every binary builds and passes its
smoke test (`--version`, `--help`, `init` and `install` against the public registry).

## Steps

1. On a branch with a PR, let [commitizen](https://commitizen-tools.github.io/commitizen/) pick
   the next version from the [Conventional Commits](https://www.conventionalcommits.org/) since
   the last tag, then refresh the lock file:

   ```bash
   uv run cz bump --files-only --yes                    # e.g. 0.2.0
   uv run cz bump --files-only --yes --prerelease rc    # or a pre-release, e.g. 0.2.0rc1
   uv lock
   ```

   This bumps `version` in `pyproject.toml` and moves the `Unreleased` entries in
   [`CHANGELOG.md`](CHANGELOG.md) under the new version. `--files-only` stops it from committing
   or tagging, since the tag belongs on `main` (step 2). Edit the changelog wording if it needs it.
   Use `uv run cz bump --dry-run` to preview, or `uv run cz changelog` to regenerate the
   `Unreleased` section between releases.
2. Once it's merged, tag `main` with the same version and push the tag:

   ```bash
   git switch main && git pull
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. Approve the `pypi` deployment in the workflow run if the environment requires approval.

If the tag doesn't match `pyproject.toml`, the workflow stops before publishing anything. Delete
the tag (`git push --delete origin v0.2.0 && git tag -d v0.2.0`), fix, and tag again.

Versions with `a`, `b` or `rc` (e.g. `0.2.0rc1`) are marked as pre-releases. `pipx install
itqan-cli` skips them unless asked for explicitly: `pipx install itqan-cli==0.2.0rc1`.

## One-time setup

- **PyPI:** under the project (or, before the first release, under *Your account →
  Publishing → Add a pending publisher*), add a GitHub trusted publisher:
  - Project name: `itqan-cli`
  - Owner: `Itqan-community`
  - Repository: `itqan-cli`
  - Workflow: `release.yml`
  - Environment: `pypi`
- **GitHub:** create an environment named `pypi` under *Settings → Environments*. Adding required
  reviewers makes every release wait for a maintainer's approval.
- **Homebrew:** after a final (not pre-) release, the `homebrew` job regenerates
  `Formula/itqan.rb` in [`Itqan-community/homebrew-tap`](https://github.com/Itqan-community/homebrew-tap)
  with [`scripts/homebrew_formula.py`](scripts/homebrew_formula.py) and pushes it. It pushes with
  an SSH deploy key, so no personal token is stored:

  ```bash
  ssh-keygen -t ed25519 -N "" -C "itqan-cli release" -f tap_key
  gh repo deploy-key add tap_key.pub --repo Itqan-community/homebrew-tap --allow-write --title "itqan-cli release"
  gh secret set HOMEBREW_TAP_DEPLOY_KEY --repo Itqan-community/itqan-cli < tap_key
  rm tap_key tap_key.pub
  ```

  If the job fails, the release is still out on PyPI and GitHub; fix the cause and re-run the job.

# Releasing

Releases are published by [`.github/workflows/release.yml`](.github/workflows/release.yml) when a
version tag is pushed. It runs the tests, builds the package, publishes it to
[PyPI](https://pypi.org/project/itqan-cli/) and creates the GitHub Release.

## Steps

1. Bump `version` in `pyproject.toml` (e.g. `0.2.0`, or `0.2.0rc1` for a pre-release) and run
   `uv lock`, on a branch with a PR.
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

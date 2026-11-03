"""`itqan autoupdate`: write the scheduled GitHub Actions workflow that opens asset-update PRs."""

from pathlib import Path

from click.testing import CliRunner
import pytest
import yaml

from itqan_cli.main import cli

WORKFLOW = Path(".github/workflows/update-itqan-assets.yml")
MANIFEST = "schema_version: 1\nassets: {}\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A git repository root holding a manifest, as the current folder."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "itqan-assets.yaml").write_text(MANIFEST)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(*args: str):
    return CliRunner().invoke(cli, ["autoupdate", *args])


def _steps(root: Path) -> list[dict]:
    workflow = yaml.safe_load((root / WORKFLOW).read_text())
    return workflow["jobs"]["update"]["steps"]


def _install_step(root: Path) -> dict:
    return next(step for step in _steps(root) if "run" in step)


def test_writes_the_workflow_at_the_repository_root(repo):
    result = _run()

    assert result.exit_code == 0, result.output
    assert f"Created {WORKFLOW.as_posix()}." in result.output
    assert "Allow GitHub Actions to create and approve pull requests" in result.output
    workflow = yaml.safe_load((repo / WORKFLOW).read_text())
    # PyYAML reads the `on:` key as the boolean True.
    assert workflow[True]["schedule"] == [{"cron": "0 6 * * 1"}]
    assert "workflow_dispatch" in workflow[True]
    assert workflow["permissions"] == {"contents": "write", "pull-requests": "write"}
    steps = _steps(repo)
    assert [s.get("uses", "").split("@")[0] for s in steps] == [
        "actions/checkout",
        "itqan-community/setup-itqan",
        "",
        "peter-evans/create-pull-request",
    ]
    install = _install_step(repo)
    assert install["run"] == "itqan install --force"
    assert "working-directory" not in install
    assert install["env"] == {"ITQAN_API_KEY": "${{ secrets.ITQAN_API_KEY }}"}
    assert steps[-1]["with"]["branch"] == "itqan/update-assets"


def test_refuses_to_overwrite_without_force(repo):
    assert _run().exit_code == 0
    (repo / WORKFLOW).write_text("# mine\n")

    result = _run()
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert (repo / WORKFLOW).read_text() == "# mine\n"

    assert _run("--force").exit_code == 0
    assert (repo / WORKFLOW).read_text() != "# mine\n"


def test_fails_without_a_manifest(repo):
    (repo / "itqan-assets.yaml").unlink()

    result = _run()

    assert result.exit_code == 1
    assert "No manifest found" in result.output
    assert not (repo / WORKFLOW).exists()


def test_runs_from_the_current_subfolder(repo, monkeypatch):
    app = repo / "apps" / "my app"
    app.mkdir(parents=True)
    (app / "itqan-assets.yaml").write_text(MANIFEST)
    monkeypatch.chdir(app)

    result = _run()

    assert result.exit_code == 0, result.output
    install = _install_step(repo)
    assert install["working-directory"] == "apps/my app"
    assert install["run"] == "itqan install --force"


def test_passes_non_default_manifest_and_lockfile(repo):
    (repo / "config").mkdir()
    (repo / "config" / "assets.yaml").write_text(MANIFEST)

    result = _run("-m", "config/assets.yaml", "-l", str(repo / "config" / "assets lock"))

    assert result.exit_code == 0, result.output
    assert _install_step(repo)["run"] == "itqan install --force -m config/assets.yaml -l 'config/assets lock'"


def test_rejects_a_manifest_outside_the_repository(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("elsewhere") / "itqan-assets.yaml"
    outside.write_text(MANIFEST)

    result = _run("-m", str(outside))

    assert result.exit_code == 1
    assert "outside the repository" in result.output


def test_adds_flutter_in_a_flutter_project(repo):
    (repo / "pubspec.yaml").write_text("name: app\nflutter:\n  uses-material-design: true\n")

    assert _run().exit_code == 0
    assert _install_step(repo)["run"] == "itqan install --force --flutter"

    assert _run("--force", "--no-flutter").exit_code == 0
    assert _install_step(repo)["run"] == "itqan install --force"


def test_flutter_flag_without_a_pubspec(repo):
    assert _run("--flutter").exit_code == 0
    assert _install_step(repo)["run"] == "itqan install --force --flutter"


def test_custom_schedule(repo):
    result = _run("--schedule", "30  2 * * *")

    assert result.exit_code == 0, result.output
    assert yaml.safe_load((repo / WORKFLOW).read_text())[True]["schedule"] == [{"cron": "30 2 * * *"}]


@pytest.mark.parametrize("schedule", ["daily", "0 6 * *", "0 6 * * 1 2", '0 6 * * "1"'])
def test_rejects_a_bad_schedule(repo, schedule):
    result = _run("--schedule", schedule)

    assert result.exit_code == 1
    assert "cron expression" in result.output
    assert not (repo / WORKFLOW).exists()


def test_custom_output_path(repo):
    result = _run("-o", "ci/itqan.yml")

    assert result.exit_code == 0, result.output
    assert "Created ci/itqan.yml." in result.output
    assert (repo / "ci" / "itqan.yml").is_file()
    assert not (repo / WORKFLOW).exists()


def test_finds_the_repository_from_a_worktree_git_file(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text("gitdir: /somewhere/else\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "itqan-assets.yaml").write_text(MANIFEST)
    monkeypatch.chdir(tmp_path / "pkg")

    assert _run().exit_code == 0
    assert _install_step(tmp_path)["working-directory"] == "pkg"


def test_outside_a_repository_uses_the_current_folder(tmp_path, monkeypatch):
    (tmp_path / "itqan-assets.yaml").write_text(MANIFEST)
    monkeypatch.chdir(tmp_path)

    result = _run()

    assert result.exit_code == 0, result.output
    assert "not in a git repository" in result.output
    assert (tmp_path / WORKFLOW).is_file()

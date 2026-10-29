"""A dry run must never write to GitHub, even when a token is available."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from cli import main as cli_main
from core import git_operations
from core.git_operations import GitManager

FAKE_TOKEN = "fake-token"


class StopFlow(Exception):
    pass


@pytest.fixture
def git_commands(monkeypatch):
    commands = []

    def fake_run_git_command(cmd, cwd=None, debug=False):
        commands.append(list(cmd))
        # Mimic a fresh clone: no local or remote feature branch exists yet
        if cmd[:3] == ["git", "branch", "-D"] or cmd[:3] == ["git", "rev-parse", "--verify"]:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(git_operations, "run_git_command", fake_run_git_command)
    return commands


@pytest.fixture
def github_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(git_operations, "Github", MagicMock(return_value=client))
    return client


def assert_no_github_writes(commands, github_client):
    assert not any(cmd[:2] == ["git", "push"] for cmd in commands)
    github_client.get_user.return_value.create_fork.assert_not_called()
    github_client.get_repo.return_value.create_pull.assert_not_called()


def test_dry_run_clones_upstream_without_forking_or_pushing(git_commands, github_client):
    with GitManager(FAKE_TOKEN, dry_run=True) as git_mgr:
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()
        git_mgr.create_branch(infra_repo_path, "some-branch-infra")
        git_mgr.create_branch(main_repo_path, "some-branch-main")

    assert_no_github_writes(git_commands, github_client)
    clone_urls = [cmd[2] for cmd in git_commands if cmd[:2] == ["git", "clone"]]
    assert clone_urls == [
        f"https://github.com/{GitManager.CE_MAIN_REPO}.git",
        f"https://github.com/{GitManager.CE_INFRA_REPO}.git",
    ]
    assert ["git", "checkout", "-b", "some-branch-infra"] in git_commands
    assert ["git", "checkout", "-b", "some-branch-main"] in git_commands


def test_dry_run_refuses_push_and_pull_request(git_commands, github_client):
    with GitManager(FAKE_TOKEN, dry_run=True) as git_mgr:
        main_repo_path, _ = git_mgr.clone_repositories()
        with pytest.raises(RuntimeError):
            git_mgr.push_branch(main_repo_path, "some-branch-main")
        with pytest.raises(RuntimeError):
            git_mgr.create_pull_request(GitManager.CE_MAIN_REPO, "some-branch-main", "t", "b")

    assert_no_github_writes(git_commands, github_client)


def test_non_dry_run_with_token_still_uses_fork(git_commands, github_client):
    github_client.get_user.return_value.login = "someone"
    github_client.get_repo.side_effect = lambda name: MagicMock(full_name=name)

    with GitManager(FAKE_TOKEN) as git_mgr:
        main_repo_path, _ = git_mgr.clone_repositories()
        git_mgr.create_branch(main_repo_path, "some-branch-main")

    clone_urls = [cmd[2] for cmd in git_commands if cmd[:2] == ["git", "clone"]]
    assert clone_urls == [
        "https://github.com/someone/compiler-explorer.git",
        "https://github.com/someone/infra.git",
    ]
    assert ["git", "push", "origin", "main"] in git_commands


FLOWS = [
    pytest.param(lambda **kw: cli_main.process_cpp_library(MagicMock(), **kw), id="cpp"),
    pytest.param(lambda **kw: cli_main.process_c_library(MagicMock(), **kw), id="c"),
    pytest.param(lambda **kw: cli_main.process_rust_library(MagicMock(), **kw), id="rust"),
    pytest.param(lambda **kw: cli_main.process_top_rust_crates(**kw), id="top-rust-crates"),
    pytest.param(lambda **kw: cli_main.process_fortran_library(MagicMock(), **kw), id="fortran"),
    pytest.param(lambda **kw: cli_main.process_go_library(MagicMock(), **kw), id="go"),
]


@pytest.mark.parametrize("run_flow", FLOWS)
def test_every_flow_makes_no_github_writes_in_dry_run(
    run_flow, git_commands, github_client, monkeypatch
):
    # Run each flow's real clone and branch steps, then stop before the language handler
    original_create_branch = GitManager.create_branch
    branches_created = []

    def create_branch_then_stop(self, repo_path, branch_name):
        original_create_branch(self, repo_path, branch_name)
        branches_created.append(branch_name)
        if len(branches_created) == 2:
            raise StopFlow

    monkeypatch.setattr(GitManager, "create_branch", create_branch_then_stop)

    with pytest.raises(StopFlow):
        run_flow(github_token=FAKE_TOKEN, dry_run=True, yes=True)

    assert len(branches_created) == 2
    assert_no_github_writes(git_commands, github_client)

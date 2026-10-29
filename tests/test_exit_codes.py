"""A run that doesn't finish what it was asked to do must exit non-zero."""
from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from cli import main as cli_main

GO_ARGS = ["--lang", "go", "--lib", "example.com/mod", "--ver", "v1.0.0", "--build-test", "no"]
RUST_ARGS = ["--lang", "rust", "--lib", "serde", "--ver", "1.0.0"]


@pytest.fixture(autouse=True)
def no_github_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(cli_main, "get_github_token_via_gh_cli", lambda: None)


def run(args, **kwargs):
    return CliRunner().invoke(cli_main.main, args, **kwargs)


@pytest.fixture
def go_flow_until_commit(monkeypatch):
    """Run the Go flow for real up to the commit, with no network, git or ce_install."""
    monkeypatch.setattr(
        cli_main, "resolve_go_module", lambda module, version: ("example.com/mod", None)
    )
    monkeypatch.setattr(cli_main, "detect_import_path", lambda module, version: None)

    git_mgr = MagicMock()
    git_mgr.clone_repositories.return_value = (Path("main"), Path("infra"))
    git_mgr.get_diff.return_value = "a diff"
    git_mgr.commit_changes.return_value = False
    git_manager = MagicMock()
    git_manager.return_value.__enter__.return_value = git_mgr
    monkeypatch.setattr(cli_main, "GitManager", git_manager)

    go_handler = MagicMock()
    go_handler.add_library.return_value = "mod"
    go_handler.update_go_properties.return_value = True
    monkeypatch.setattr(cli_main, "GoHandler", MagicMock(return_value=go_handler))
    return git_mgr


# --- Failures inside a process function ---


def test_go_module_resolution_error_exits_1():
    def urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        result = run([*GO_ARGS, "-y", "--dry-run"])

    assert result.exit_code == 1
    assert "Go module proxy has no module example.com/mod" in result.stderr


def test_declined_confirmation_exits_1(go_flow_until_commit):
    result = run([*GO_ARGS, "--verify"], input="n\n")

    assert result.exit_code == 1
    assert "Changes cancelled." in result.output
    go_flow_until_commit.commit_changes.assert_not_called()


def test_failed_version_still_processes_the_rest_then_exits_1(monkeypatch):
    process_library = MagicMock(side_effect=[False, True])
    monkeypatch.setattr(cli_main, "process_library", process_library)

    result = run(["--lang", "rust", "--lib", "serde", "--ver", "1.0.0,2.0.0"])

    assert result.exit_code == 1
    assert [c.args[0].version for c in process_library.call_args_list] == ["1.0.0", "2.0.0"]


def test_failed_top_rust_crates_exits_1(monkeypatch):
    monkeypatch.setattr(cli_main, "process_top_rust_crates", MagicMock(return_value=False))

    assert run(["--top-rust-crates", "-y"]).exit_code == 1


# --- Exceptions caught by main ---


def test_unexpected_exception_exits_1(monkeypatch):
    monkeypatch.setattr(cli_main, "process_library", MagicMock(side_effect=RuntimeError("boom")))

    result = run(RUST_ARGS)

    assert result.exit_code == 1
    assert "Error: boom" in result.stderr


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, click.exceptions.Abort])
def test_ctrl_c_exits_130(monkeypatch, interrupt):
    monkeypatch.setattr(cli_main, "process_library", MagicMock(side_effect=interrupt))

    result = run(RUST_ARGS)

    assert result.exit_code == 130
    assert "Cancelled by user." in result.output


def test_failed_oauth_exits_1(monkeypatch):
    monkeypatch.setattr(cli_main, "get_github_token_via_oauth", lambda: None)

    result = run([*RUST_ARGS, "--oauth"])

    assert result.exit_code == 1
    assert "Failed to authenticate" in result.stderr


# --- Successful runs ---


def test_dry_run_exits_0(go_flow_until_commit):
    result = run([*GO_ARGS, "-y", "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run complete" in result.output


def test_version_already_present_exits_0(go_flow_until_commit):
    result = run([*GO_ARGS, "-y"])

    assert result.exit_code == 0
    assert "Library version already exists - no changes to commit." in result.output


def test_committed_without_github_token_exits_1(go_flow_until_commit):
    go_flow_until_commit.commit_changes.return_value = True

    result = run([*GO_ARGS, "-y"])

    assert result.exit_code == 1
    assert "No GitHub authentication found" in result.output

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from pathlib import Path

from github import Github

from .subprocess_utils import run_git_command

logger = logging.getLogger(__name__)


class GitManager:
    """Manages git operations for compiler-explorer repositories"""

    CE_MAIN_REPO = "compiler-explorer/compiler-explorer"
    CE_INFRA_REPO = "compiler-explorer/infra"

    def __init__(
        self, github_token: str | None = None, debug: bool = False, keep_temp: bool = False
    ):
        self.github_token = github_token
        self.debug = debug
        self.keep_temp = keep_temp
        self.temp_dir = None
        self.main_repo_path = None
        self.infra_repo_path = None
        self.user_main_repo = None
        self.user_infra_repo = None
        self.github_client = None

        if self.github_token:
            self.github_client = Github(self.github_token)

    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ce-lib-wizard-")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and Path(self.temp_dir).exists():
            if self.keep_temp:
                logger.info(f"Keeping temporary directory: {self.temp_dir}")
            else:
                try:
                    shutil.rmtree(self.temp_dir, ignore_errors=True)
                except Exception:  # noqa: S110
                    pass  # Best effort cleanup

    def _run_git_command(self, cmd: list, cwd: str | None = None):
        """Run a git command and return the result"""
        working_dir = cwd or self.temp_dir
        return run_git_command(cmd, cwd=working_dir, debug=self.debug)

    def _ensure_fork_exists(self, original_repo: str) -> str:
        """Ensure user has a fork of the repository, create if needed"""
        if not self.github_client:
            raise ValueError("GitHub token required for forking repositories")

        user = self.github_client.get_user()
        username = user.login

        # Check if fork already exists
        try:
            fork = self.github_client.get_repo(f"{username}/{original_repo.split('/')[1]}")
            print(f"✓ Using existing fork: {fork.full_name}")
            return fork.full_name
        except Exception:
            # Fork doesn't exist, create it
            print(f"Creating fork of {original_repo}...")
            original = self.github_client.get_repo(original_repo)
            fork = user.create_fork(original)

            # Wait a bit for the fork to be ready
            print("Waiting for fork to be ready...")
            time.sleep(5)
            return fork.full_name

    def clone_repositories(self) -> tuple[Path, Path]:
        """Clone both compiler-explorer repositories (from user's forks if using token)"""
        self.main_repo_path = Path(self.temp_dir) / "compiler-explorer"
        self.infra_repo_path = Path(self.temp_dir) / "infra"

        # Ensure directories don't exist
        if self.main_repo_path.exists():
            shutil.rmtree(self.main_repo_path)
        if self.infra_repo_path.exists():
            shutil.rmtree(self.infra_repo_path)

        # Determine which repos to clone
        if self.github_token:
            # Ensure forks exist and clone from user's forks
            self.user_main_repo = self._ensure_fork_exists(self.CE_MAIN_REPO)
            self.user_infra_repo = self._ensure_fork_exists(self.CE_INFRA_REPO)

            main_clone_url = f"https://github.com/{self.user_main_repo}.git"
            infra_clone_url = f"https://github.com/{self.user_infra_repo}.git"
        else:
            # No token, clone from original repos (won't be able to push)
            main_clone_url = f"https://github.com/{self.CE_MAIN_REPO}.git"
            infra_clone_url = f"https://github.com/{self.CE_INFRA_REPO}.git"

        # Clone main repository
        self._run_git_command(["git", "clone", main_clone_url, str(self.main_repo_path)])

        # Clone infra repository
        self._run_git_command(["git", "clone", infra_clone_url, str(self.infra_repo_path)])

        # C++ library commands are now available in main branch

        # Add upstream remotes if we're using forks
        if self.github_token:
            # Add upstream remote for main repo
            self._run_git_command(
                ["git", "remote", "add", "upstream", f"https://github.com/{self.CE_MAIN_REPO}.git"],
                cwd=str(self.main_repo_path),
            )

            # Add upstream remote for infra repo
            self._run_git_command(
                [
                    "git",
                    "remote",
                    "add",
                    "upstream",
                    f"https://github.com/{self.CE_INFRA_REPO}.git",
                ],
                cwd=str(self.infra_repo_path),
            )

        return self.main_repo_path, self.infra_repo_path

    def create_branch(self, repo_path: Path, branch_name: str):
        """Create a new branch in the given repository, syncing with upstream and origin first"""
        # If we have a GitHub token (meaning we're using forks), sync everything first
        if self.github_token:
            try:
                print(f"🔄 Syncing {repo_path.name} with upstream and origin...")

                # Fetch from all remotes to get latest changes
                self._run_git_command(["git", "fetch", "upstream"], cwd=str(repo_path))
                self._run_git_command(["git", "fetch", "origin"], cwd=str(repo_path))

                # Make sure we're on main branch
                self._run_git_command(["git", "checkout", "main"], cwd=str(repo_path))

                # Merge upstream/main into our local main (get latest from original repo)
                self._run_git_command(["git", "merge", "upstream/main"], cwd=str(repo_path))

                # Also merge origin/main in case our fork has changes (this handles the fork sync)
                try:
                    self._run_git_command(["git", "merge", "origin/main"], cwd=str(repo_path))
                except Exception:
                    # This might fail if origin/main is behind upstream/main, which is fine
                    logger.info(f"Origin/main merge not needed for {repo_path.name}")

                # Push updated main to our fork to keep it in sync
                self._run_git_command(["git", "push", "origin", "main"], cwd=str(repo_path))

                print(f"✓ Successfully synced {repo_path.name}")

            except Exception as e:
                # If syncing fails, log warning but continue
                logger.warning(f"Failed to sync with upstream for {repo_path.name}: {e!s}")
                print(f"⚠️  Warning: Could not fully sync {repo_path.name}: {e}")

        # Check if the branch already exists locally, delete it if so
        try:
            self._run_git_command(["git", "branch", "-D", branch_name], cwd=str(repo_path))
            print(f"🗑️  Deleted existing local branch: {branch_name}")
        except Exception:
            # Branch doesn't exist locally, that's fine
            pass

        # Check if the branch exists on origin and handle it
        try:
            self._run_git_command(
                ["git", "rev-parse", "--verify", f"origin/{branch_name}"], cwd=str(repo_path)
            )
            # Branch exists on origin, check it out and merge latest main
            print(f"📥 Branch {branch_name} exists on origin, checking out and updating...")
            self._run_git_command(
                ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"], cwd=str(repo_path)
            )
            # Merge the latest main into this branch to ensure it's up to date
            self._run_git_command(["git", "merge", "main"], cwd=str(repo_path))
            print(f"✓ Updated existing branch {branch_name} with latest main")
        except Exception:
            # Branch doesn't exist on origin, create it from main
            self._run_git_command(["git", "checkout", "-b", branch_name], cwd=str(repo_path))

    def get_diff(self, repo_path: Path) -> str:
        """Get the git diff for uncommitted changes"""
        try:
            result = self._run_git_command(["git", "diff", "--cached"], cwd=str(repo_path))
            staged_diff = result.stdout

            result = self._run_git_command(["git", "diff"], cwd=str(repo_path))
            unstaged_diff = result.stdout

            # Combine both staged and unstaged changes
            full_diff = ""
            if staged_diff:
                full_diff += staged_diff
            if unstaged_diff:
                if full_diff:
                    full_diff += "\n"
                full_diff += unstaged_diff

            return full_diff
        except Exception:
            return ""

    def commit_changes(self, repo_path: Path, message: str):
        """Stage all changes and commit if there are changes"""
        # Stage all changes
        self._run_git_command(["git", "add", "-A"], cwd=str(repo_path))

        # Check if there are changes to commit
        try:
            self._run_git_command(["git", "diff", "--cached", "--quiet"], cwd=str(repo_path))
            # If git diff --cached --quiet succeeds (exit code 0), there are no staged changes
            logger.info(f"No changes to commit in {repo_path.name}")
            return False
        except Exception:
            # If git diff --cached --quiet fails (exit code 1), there are staged changes
            self._run_git_command(["git", "commit", "-m", message], cwd=str(repo_path))
            return True

    def push_branch(self, repo_path: Path, branch_name: str, remote_name: str = "origin"):
        """Push branch to remote"""
        if self.github_token:
            # Get the current remote URL
            result = self._run_git_command(
                ["git", "remote", "get-url", remote_name], cwd=str(repo_path)
            )
            remote_url = result.stdout.strip()

            # Configure remote with token
            if remote_url.startswith("https://"):
                auth_url = remote_url.replace("https://", f"https://{self.github_token}@")
                self._run_git_command(
                    ["git", "remote", "set-url", remote_name, auth_url], cwd=str(repo_path)
                )

        self._run_git_command(
            ["git", "push", remote_name, f"{branch_name}:{branch_name}"], cwd=str(repo_path)
        )

    def create_pull_request(
        self, upstream_repo: str, branch_name: str, title: str, body: str
    ) -> str:
        """Create a pull request from user's fork to upstream"""
        if not self.github_client:
            raise ValueError("GitHub token required to create pull requests")

        # Get the upstream repository
        upstream = self.github_client.get_repo(upstream_repo)

        # Get user's username for the head reference
        user = self.github_client.get_user()
        username = user.login

        # Create pull request from user's fork to upstream
        pr = upstream.create_pull(
            title=title,
            body=body,
            head=f"{username}:{branch_name}",  # Format: username:branch
            base="main",
        )

        return pr.html_url

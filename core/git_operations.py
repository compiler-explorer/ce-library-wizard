import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Tuple, Optional

from github import Github
from .subprocess_utils import run_git_command

logger = logging.getLogger(__name__)


class GitManager:
    """Manages git operations for compiler-explorer repositories"""
    
    CE_MAIN_REPO = "compiler-explorer/compiler-explorer"
    CE_INFRA_REPO = "compiler-explorer/infra"
    
    def __init__(self, github_token: Optional[str] = None, debug: bool = False):
        self.github_token = github_token
        self.debug = debug
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
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except:
                pass  # Best effort cleanup
    
    def _run_git_command(self, cmd: list, cwd: str = None):
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
        except:
            # Fork doesn't exist, create it
            print(f"Creating fork of {original_repo}...")
            original = self.github_client.get_repo(original_repo)
            fork = user.create_fork(original)
            
            # Wait a bit for the fork to be ready
            print("Waiting for fork to be ready...")
            time.sleep(5)
            return fork.full_name
    
    def clone_repositories(self) -> Tuple[Path, Path]:
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
        self._run_git_command([
            "git", "clone",
            main_clone_url,
            str(self.main_repo_path)
        ])
        
        # Clone infra repository
        self._run_git_command([
            "git", "clone",
            infra_clone_url,
            str(self.infra_repo_path)
        ])
        
        # C++ library commands are now available in main branch
        
        # Add upstream remotes if we're using forks
        if self.github_token:
            # Add upstream remote for main repo
            self._run_git_command([
                "git", "remote", "add", "upstream",
                f"https://github.com/{self.CE_MAIN_REPO}.git"
            ], cwd=str(self.main_repo_path))
            
            # Add upstream remote for infra repo
            self._run_git_command([
                "git", "remote", "add", "upstream",
                f"https://github.com/{self.CE_INFRA_REPO}.git"
            ], cwd=str(self.infra_repo_path))
        
        return self.main_repo_path, self.infra_repo_path
    
    def create_branch(self, repo_path: Path, branch_name: str):
        """Create a new branch in the given repository, syncing with upstream first"""
        # If we have a GitHub token (meaning we're using forks), sync with upstream first
        if self.github_token:
            try:
                # Fetch from upstream to get latest changes
                self._run_git_command(["git", "fetch", "upstream"], cwd=str(repo_path))
                
                # Make sure we're on main branch
                self._run_git_command(["git", "checkout", "main"], cwd=str(repo_path))
                
                # Merge upstream/main into our local main
                self._run_git_command(["git", "merge", "upstream/main"], cwd=str(repo_path))
                
                # Push updated main to our fork
                self._run_git_command(["git", "push", "origin", "main"], cwd=str(repo_path))
                
            except Exception as e:
                # If syncing fails, log warning but continue - user might not have upstream configured
                logger.warning(f"Failed to sync with upstream for {repo_path.name}: {e}")
        
        # Create the new branch from the (hopefully updated) main
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
        except:
            return ""
    
    def commit_changes(self, repo_path: Path, message: str):
        """Stage all changes and commit if there are changes"""
        # Stage all changes
        self._run_git_command(["git", "add", "-A"], cwd=str(repo_path))
        
        # Check if there are changes to commit
        try:
            result = self._run_git_command(["git", "diff", "--cached", "--quiet"], cwd=str(repo_path))
            # If git diff --cached --quiet succeeds (exit code 0), there are no staged changes
            logger.info(f"No changes to commit in {repo_path.name}")
            return False
        except:
            # If git diff --cached --quiet fails (exit code 1), there are staged changes
            self._run_git_command(["git", "commit", "-m", message], cwd=str(repo_path))
            return True
    
    def push_branch(self, repo_path: Path, branch_name: str, remote_name: str = "origin"):
        """Push branch to remote"""
        if self.github_token:
            # Get the current remote URL
            result = self._run_git_command(
                ["git", "remote", "get-url", remote_name], 
                cwd=str(repo_path)
            )
            remote_url = result.stdout.strip()
            
            # Configure remote with token
            if remote_url.startswith("https://"):
                auth_url = remote_url.replace(
                    "https://",
                    f"https://{self.github_token}@"
                )
                self._run_git_command(
                    ["git", "remote", "set-url", remote_name, auth_url],
                    cwd=str(repo_path)
                )
        
        self._run_git_command(
            ["git", "push", remote_name, f"{branch_name}:{branch_name}"],
            cwd=str(repo_path)
        )
    
    def create_pull_request(self, upstream_repo: str, branch_name: str, 
                          title: str, body: str) -> str:
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
            base="main"
        )
        
        return pr.html_url
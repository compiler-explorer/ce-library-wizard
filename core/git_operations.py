from typing import Tuple, Optional
from pathlib import Path
import tempfile
import shutil
from git import Repo
from github import Github


class GitManager:
    """Manages git operations for compiler-explorer repositories"""
    
    CE_MAIN_REPO = "compiler-explorer/compiler-explorer"
    CE_INFRA_REPO = "compiler-explorer/infra"
    
    def __init__(self, github_token: Optional[str] = None):
        self.github_token = github_token
        self.temp_dir = None
        self.main_repo = None
        self.infra_repo = None
    
    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ce-lib-wizard-")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
    
    def clone_repositories(self) -> Tuple[Path, Path]:
        """Clone both compiler-explorer repositories"""
        main_path = Path(self.temp_dir) / "compiler-explorer"
        infra_path = Path(self.temp_dir) / "infra"
        
        # Clone main repository
        self.main_repo = Repo.clone_from(
            f"https://github.com/{self.CE_MAIN_REPO}.git",
            main_path,
            depth=1
        )
        
        # Clone infra repository
        self.infra_repo = Repo.clone_from(
            f"https://github.com/{self.CE_INFRA_REPO}.git",
            infra_path,
            depth=1
        )
        
        return main_path, infra_path
    
    def create_branch(self, repo: Repo, branch_name: str):
        """Create a new branch in the given repository"""
        repo.create_head(branch_name)
        repo.heads[branch_name].checkout()
    
    def commit_changes(self, repo: Repo, message: str):
        """Stage all changes and commit"""
        repo.git.add(A=True)
        repo.index.commit(message)
    
    def push_branch(self, repo: Repo, branch_name: str, remote_name: str = "origin"):
        """Push branch to remote"""
        if self.github_token:
            # Configure remote with token
            remote_url = repo.remotes[remote_name].url
            if remote_url.startswith("https://"):
                auth_url = remote_url.replace(
                    "https://",
                    f"https://{self.github_token}@"
                )
                repo.remotes[remote_name].set_url(auth_url)
        
        repo.remotes[remote_name].push(refspec=f"{branch_name}:{branch_name}")
    
    def create_pull_request(self, repo_name: str, branch_name: str, 
                          title: str, body: str) -> str:
        """Create a pull request using GitHub API"""
        if not self.github_token:
            raise ValueError("GitHub token required to create pull requests")
        
        g = Github(self.github_token)
        repo = g.get_repo(repo_name)
        
        pr = repo.create_pull(
            title=title,
            body=body,
            head=branch_name,
            base="main"
        )
        
        return pr.html_url
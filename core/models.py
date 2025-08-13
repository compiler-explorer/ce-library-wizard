from __future__ import annotations

import subprocess
import tempfile
import urllib.request
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, HttpUrl, field_validator

from .subprocess_utils import run_command


class Language(str, Enum):
    C = "C"
    CPP = "C++"
    RUST = "Rust"
    FORTRAN = "Fortran"


class BuildTool(str, Enum):
    CMAKE = "cmake"
    MAKE = "make"


class LinkType(str, Enum):
    SHARED = "shared"
    STATIC = "static"


class LibraryType(str, Enum):
    HEADER_ONLY = "header-only"
    PACKAGED_HEADERS = "packaged-headers"
    STATIC = "static"
    SHARED = "shared"
    CSHARED = "cshared"


def extract_github_repo_info(github_url: str) -> tuple[str, str] | None:
    """Extract owner and repo name from GitHub URL"""
    if not github_url:
        return None

    # Handle various GitHub URL formats
    url = github_url.rstrip("/")
    if url.startswith("https://github.com/"):
        path = url[len("https://github.com/") :]
    elif url.startswith("http://github.com/"):
        path = url[len("http://github.com/") :]
    elif url.startswith("github.com/"):
        path = url[len("github.com/") :]
    else:
        return None

    parts = path.split("/")
    if len(parts) >= 2:
        return parts[0], parts[1]
    return None


def check_github_release_exists(github_url: str, version: str) -> bool:
    """Check if a GitHub release/tag exists using GitHub API"""
    repo_info = extract_github_repo_info(github_url)
    if not repo_info:
        return False

    owner, repo = repo_info

    # Check the exact version specified
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{version}"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status == 200:
                return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        # Try checking tags endpoint if releases endpoint fails
        tag_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/tags/{version}"
        try:
            with urllib.request.urlopen(tag_url, timeout=10) as tag_response:
                if tag_response.status == 200:
                    return True
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            pass

    return False


def check_git_tag_exists(repo_url: str, tag: str) -> bool:
    """Check if a git tag exists in the remote repository (exact match only)"""
    # First try GitHub API if it's a GitHub URL
    if "github.com" in repo_url:
        if check_github_release_exists(repo_url, tag):
            return True

    # Fallback to git ls-remote for non-GitHub repos or if API fails
    try:
        # Check if tag exists remotely without cloning
        result = subprocess.run(
            ["git", "ls-remote", "--tags", repo_url, f"refs/tags/{tag}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0 and result.stdout.strip() != ""
    except (subprocess.TimeoutExpired, subprocess.SubprocessError):
        return False


def check_git_tag_with_fallback(repo_url: str, tag: str) -> bool:
    """Check if a git tag exists, trying with 'v' prefix as fallback if not found"""
    # First check exact tag
    if check_git_tag_exists(repo_url, tag):
        return True

    # If not found and doesn't start with 'v', try with 'v' prefix
    if not tag.startswith("v"):
        return check_git_tag_exists(repo_url, f"v{tag}")

    return False


def check_existing_library_config(
    repo_url: str, library_id: str, infra_repo_path: Path | None = None
) -> dict | None:
    """
    Check if a library already exists in libraries.yaml and return its configuration.
    Returns None if not found, or a dict with the library configuration if found.
    """
    if not infra_repo_path:
        return None

    libraries_yaml_path = infra_repo_path / "bin" / "yaml" / "libraries.yaml"

    if not libraries_yaml_path.exists():
        return None

    try:
        with open(libraries_yaml_path, encoding="utf-8") as f:
            libraries_data = yaml.safe_load(f)

        if not isinstance(libraries_data, dict):
            return None

        # The structure is: libraries -> language -> library_name
        libraries_section = libraries_data.get("libraries", {})
        if not libraries_section:
            return None

        # Check in different language sections (c, cpp, rust, etc.)
        for lang_libs in libraries_section.values():
            if not isinstance(lang_libs, dict):
                continue

            # Check if library_id exists in this language section
            if library_id in lang_libs:
                return lang_libs[library_id]

            # Also check by GitHub URL/repo since library_id might be different
            for lib_config in lang_libs.values():
                if isinstance(lib_config, dict):
                    lib_url = lib_config.get("url")
                    lib_repo = lib_config.get("repo")

                    if lib_url == repo_url:
                        return lib_config

                    # Also check repo field which might be in format "owner/repo"
                    if lib_repo and repo_url.endswith(f"/{lib_repo}"):
                        return lib_config

        return None

    except (yaml.YAMLError, FileNotFoundError, PermissionError):
        return None


def check_existing_library_config_remote(repo_url: str, library_id: str) -> dict | None:
    """
    Check if a library already exists by temporarily cloning the infra repository.
    This is used during interactive detection when we don't have the repo yet.
    """
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            infra_path = Path(tmpdir) / "infra"

            # Clone the infra repository
            result = run_command(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "https://github.com/compiler-explorer/infra",
                    str(infra_path),
                ],
                clean_env=False,
            )

            if result.returncode != 0:
                return None

            return check_existing_library_config(repo_url, library_id, infra_path)

    except Exception:
        return None


def determine_version_format(repo_url: str, version: str) -> tuple[str, str | None, bool]:
    """
    Determine the actual version format by checking git tags.
    Returns (normalized_version, target_prefix, version_exists)
    """
    if not repo_url:
        # No repo URL, can't check tags - just normalize by removing 'v' prefix
        if version.startswith("v"):
            return version[1:], "v", False
        return version, None, False

    # Check if version starts with 'v'
    if version.startswith("v"):
        # User entered v1.2.3 - check if both v1.2.3 and 1.2.3 exist
        version_with_v = version
        version_without_v = version[1:]

        if check_git_tag_exists(repo_url, version_with_v):
            # v1.2.3 exists - use it and set target_prefix
            return version_without_v, "v", True
        elif check_git_tag_exists(repo_url, version_without_v):
            # Only 1.2.3 exists - user made a mistake, use 1.2.3
            return version_without_v, None, True
        else:
            # Neither exists - version doesn't exist
            return version_without_v, "v", False
    else:
        # User entered 1.2.3 - check if both 1.2.3 and v1.2.3 exist
        version_without_v = version
        version_with_v = f"v{version}"

        if check_git_tag_exists(repo_url, version_with_v):
            # v1.2.3 exists - should use target_prefix
            return version_without_v, "v", True
        elif check_git_tag_exists(repo_url, version_without_v):
            # Only 1.2.3 exists - use it without prefix
            return version_without_v, None, True
        else:
            # Neither exists - version doesn't exist
            return version_without_v, None, False


class LibraryConfig(BaseModel):
    language: Language
    github_url: HttpUrl | None = None
    version: str | list[str]  # Support single version or list of versions
    target_prefix: str | None = None  # Prefix for version tags (e.g., 'v')
    is_header_only: bool | None = None
    build_tool: BuildTool | None = None
    link_type: LinkType | None = None
    binary_names: list[str] | None = None
    is_c_library: bool | None = None
    name: str | None = None  # For Rust crates
    library_type: LibraryType | None = None  # For C++ libraries
    library_id: str | None = None  # Library identifier for C++
    package_install: bool | None = None  # Whether CMake package installation is needed

    @field_validator("version")
    @classmethod
    def validate_version(cls, v):
        """Validate version field - convert comma-separated string to list"""
        if isinstance(v, str):
            # Check if it contains commas (multiple versions)
            if "," in v:
                versions = [ver.strip() for ver in v.split(",") if ver.strip()]
                if not versions:
                    raise ValueError("No valid versions found in comma-separated string")
                return versions
            else:
                # Single version string
                return v.strip()
        elif isinstance(v, list):
            # List of versions
            if not v:
                raise ValueError("Version list cannot be empty")
            return [ver.strip() for ver in v if ver.strip()]
        else:
            raise ValueError("Version must be a string or list of strings")

    def normalize_versions_with_git_lookup(self) -> list[str]:
        """
        Normalize versions by checking git tags and set target_prefix if needed.
        This should be called after the model is fully populated with github_url.
        Returns list of any versions that don't exist in the repository.
        """
        if not self.github_url:
            return []

        versions = self.get_versions()
        normalized_versions = []
        target_prefix = None
        missing_versions = []

        for version in versions:
            normalized_version, prefix, exists = determine_version_format(
                str(self.github_url), version
            )
            normalized_versions.append(normalized_version)

            # Track missing versions
            if not exists:
                missing_versions.append(version)

            # Set target_prefix if any version needs it
            if prefix:
                target_prefix = prefix

        # Update the model
        if len(normalized_versions) == 1:
            self.version = normalized_versions[0]
        else:
            self.version = normalized_versions

        if target_prefix:
            self.target_prefix = target_prefix

        return missing_versions

    def validate_versions_and_exit_on_missing(self) -> None:
        """
        Validate versions for non-Rust libraries and exit with error if any are missing.
        This function handles the common pattern of checking versions and failing fast.
        """
        if self.language == Language.RUST:
            return  # Rust versions don't need git tag validation

        print("\nChecking git tags for version format...")
        missing_versions = self.normalize_versions_with_git_lookup()

        if missing_versions:
            print("❌ Error: The following versions were not found in the repository:")
            for version in missing_versions:
                print(f"   - {version}")
            print("Please check the version numbers and try again.")
            exit(1)
        else:
            print("✓ All versions found in repository")

        if self.target_prefix:
            print(f"✓ Detected version format requires target_prefix: {self.target_prefix}")

    def get_versions(self) -> list[str]:
        """Get list of versions, handling both single and multiple version cases"""
        if isinstance(self.version, str):
            return [self.version]
        return self.version

    def get_primary_version(self) -> str:
        """Get the primary (first) version for operations that need a single version"""
        versions = self.get_versions()
        return versions[0]

    def is_multi_version(self) -> bool:
        """Check if this config has multiple versions"""
        return isinstance(self.version, list) and len(self.version) > 1

    def is_c_or_cpp(self) -> bool:
        return self.language in [Language.C, Language.CPP]

    def requires_build_info(self) -> bool:
        return self.is_c_or_cpp() and self.is_header_only is False

    def is_rust(self) -> bool:
        return self.language == Language.RUST

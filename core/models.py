from __future__ import annotations

import subprocess
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, HttpUrl, field_validator


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


def check_git_tag_exists(repo_url: str, tag: str) -> bool:
    """Check if a git tag exists in the remote repository"""
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
    import tempfile

    from .subprocess_utils import run_command

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


def determine_version_format(repo_url: str, version: str) -> tuple[str, str | None]:
    """
    Determine the actual version format by checking git tags.
    Returns (normalized_version, target_prefix)
    """
    if not repo_url:
        # No repo URL, can't check tags - just normalize by removing 'v' prefix
        if version.startswith("v"):
            return version[1:], "v"
        return version, None

    # Check if version starts with 'v'
    if version.startswith("v"):
        # User entered v1.2.3 - check if both v1.2.3 and 1.2.3 exist
        version_with_v = version
        version_without_v = version[1:]

        if check_git_tag_exists(repo_url, version_with_v):
            # v1.2.3 exists - use it and set target_prefix
            return version_without_v, "v"
        elif check_git_tag_exists(repo_url, version_without_v):
            # Only 1.2.3 exists - user made a mistake, use 1.2.3
            return version_without_v, None
        else:
            # Neither exists - assume user intended v1.2.3 format
            return version_without_v, "v"
    else:
        # User entered 1.2.3 - check if both 1.2.3 and v1.2.3 exist
        version_without_v = version
        version_with_v = f"v{version}"

        if check_git_tag_exists(repo_url, version_without_v):
            # 1.2.3 exists - use it without prefix
            return version_without_v, None
        elif check_git_tag_exists(repo_url, version_with_v):
            # Only v1.2.3 exists - should use target_prefix
            return version_without_v, "v"
        else:
            # Neither exists - assume user intended 1.2.3 format
            return version_without_v, None


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

    def normalize_versions_with_git_lookup(self):
        """
        Normalize versions by checking git tags and set target_prefix if needed.
        This should be called after the model is fully populated with github_url.
        """
        if not self.github_url:
            return

        versions = self.get_versions()
        normalized_versions = []
        target_prefix = None

        for version in versions:
            normalized_version, prefix = determine_version_format(str(self.github_url), version)
            normalized_versions.append(normalized_version)

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

"""Verify that library include paths in CE properties point at real directories."""
from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .subprocess_utils import run_command

logger = logging.getLogger(__name__)

HEADER_EXTENSIONS = (".h", ".hpp", ".hxx", ".hh", ".inl", ".ipp", ".tpp")

CMAKE_NOT_HEADER_ONLY_NOTE = (
    "The repository has a CMakeLists.txt, so this may not be a header-only library: "
    "its headers may need to be installed through CMake"
)


@dataclass
class PathCheckResult:
    """Outcome of validating a library version's include paths."""

    problems: list[str] = field(default_factory=list)
    has_cmake: bool = False  # Whether the library source has a top-level CMakeLists.txt

    @property
    def ok(self) -> bool:
        return not self.problems


def has_cmake_lists(directory: Path) -> bool:
    """Check whether a library source directory has a top-level CMakeLists.txt."""
    return (directory / "CMakeLists.txt").is_file()


def get_version_paths(props_content: str, library_id: str, version: str) -> list[str]:
    """
    Get the include paths configured for a specific library version.

    Args:
        props_content: Content of a CE properties file
        library_id: The library identifier
        version: The library version (as in the .version= property, e.g. "0.7.0")

    Returns:
        List of paths from libs.{id}.versions.{vid}.path (colon-separated entries are split)
    """
    prefix = re.escape(f"libs.{library_id}.versions.")
    version_ids = re.findall(rf"^{prefix}([^.\s]+)\.version=(.*)$", props_content, re.MULTILINE)
    matching_ids = [vid for vid, ver in version_ids if ver.strip() == version]

    paths = []
    for vid in matching_ids:
        path_pattern = rf"^{prefix}{re.escape(vid)}\.path=(.*)$"
        for match in re.findall(path_pattern, props_content, re.MULTILINE):
            paths.extend(p.strip() for p in match.split(":") if p.strip())
    return paths


def is_path_under(path: str, root: str) -> bool:
    """Check whether path equals root or is located below it."""
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


def find_paths_outside_destination(paths: list[str], destination: str) -> list[str]:
    """Return the paths that are not inside the install destination."""
    return [p for p in paths if not is_path_under(p, destination)]


def directory_has_headers(directory: Path) -> bool:
    """Check whether a directory contains at least one header file (recursively)."""
    return any(f.is_file() and f.suffix in HEADER_EXTENSIONS for f in directory.rglob("*"))


def find_invalid_installed_paths(paths: list[str]) -> list[str]:
    """
    Check include paths against an actual installation on disk.

    Returns:
        Human-readable problem descriptions, empty if all paths are valid
    """
    problems = []
    for p in paths:
        path = Path(p)
        if not path.is_dir():
            problems.append(f"'{p}' does not exist")
        elif not directory_has_headers(path):
            problems.append(f"'{p}' contains no header files")
    return problems


def find_invalid_repo_paths(paths: list[str], destination: str, repo_path: Path) -> list[str]:
    """
    Check include paths against a checkout of the library repository.

    The install destination of a github-type library is a clone of the repository, so
    a path {destination}/foo must exist as {repo_path}/foo.

    Returns:
        Human-readable problem descriptions, empty if all paths are valid
    """
    problems = []
    for p in paths:
        relative = p[len(destination.rstrip("/")) :].lstrip("/")
        repo_dir = repo_path / relative
        shown = f"{relative}/" if relative else "repository root"
        if not repo_dir.is_dir():
            problems.append(f"'{p}' does not exist: the repository has no {shown}")
        elif not directory_has_headers(repo_dir):
            problems.append(f"'{p}' contains no header files ({shown} in the repository)")
    return problems


def clone_repository_at_ref(github_url: str, ref: str, clone_path: Path) -> bool:
    """Shallow-clone a repository at a given tag or branch."""
    result = run_command(
        ["git", "clone", "--depth", "1", "--branch", ref, github_url, str(clone_path)],
        clean_env=False,
    )
    if result.returncode != 0:
        logger.warning(f"Could not clone {github_url} at '{ref}': {result.stderr.strip()}")
        return False
    return True


def verify_paths_against_repository(
    paths: list[str], destination: str, github_url: str
) -> PathCheckResult | None:
    """
    Clone the library at the installed version and check the include paths exist in it.

    The ref is taken from the last component of the destination, which is the
    (possibly prefixed) version ce_install checks out, e.g. libs/foo/v1.2.3.

    Returns:
        PathCheckResult, or None if the repository could not be cloned at that ref
    """
    ref = destination.rstrip("/").rsplit("/", 1)[-1]
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / "repo"
        if not clone_repository_at_ref(github_url, ref, clone_path):
            return None
        return PathCheckResult(
            problems=find_invalid_repo_paths(paths, destination, clone_path),
            has_cmake=has_cmake_lists(clone_path),
        )


def validate_version_paths(
    props_content: str,
    library_id: str,
    version: str,
    destination: str,
    github_url: str | None = None,
    yaml_config: dict | None = None,
) -> PathCheckResult:
    """
    Validate the include paths of a library version without installing it.

    Checks that every path lies inside the ce_install destination and, for github-type
    libraries, that it exists in the repository checked out at that version.

    Args:
        props_content: Content of the CE properties file
        library_id: The library identifier
        version: The library version
        destination: Absolute install destination reported by ce_install
        github_url: GitHub URL of the library (enables the repository layout check)
        yaml_config: The library's libraries.yaml entry

    Returns:
        PathCheckResult with the problems found, empty if everything is consistent
    """
    paths = get_version_paths(props_content, library_id, version)
    if not paths:
        # Libraries using packagedheaders have no path property
        return PathCheckResult()

    outside = find_paths_outside_destination(paths, destination)
    if outside:
        return PathCheckResult(
            problems=[f"'{p}' is not inside install destination '{destination}'" for p in outside]
        )

    if not github_url or not yaml_config or yaml_config.get("type") != "github":
        return PathCheckResult()

    result = verify_paths_against_repository(paths, destination, github_url)
    if result is None:
        logger.warning("Skipping repository layout check for include paths")
        return PathCheckResult()
    return result


def override_include_path(
    props_content: str, library_id: str, version: str, include_path: str
) -> tuple[str, int]:
    """
    Replace the default include/ directory of a library version with a custom one.

    ce_install always generates {destination}/include for libraries without
    package_install; this swaps that suffix for include_path ("." for the root).

    Args:
        props_content: Content of a CE properties file
        library_id: The library identifier
        version: The library version
        include_path: Header directory relative to the repository root

    Returns:
        Tuple of (new content, number of path properties changed)
    """
    prefix = re.escape(f"libs.{library_id}.versions.")
    version_ids = re.findall(rf"^{prefix}([^.\s]+)\.version=(.*)$", props_content, re.MULTILINE)
    matching_ids = [vid for vid, ver in version_ids if ver.strip() == version]
    suffix = "" if include_path == "." else f"/{include_path}"

    changed = 0
    for vid in matching_ids:
        path_pattern = re.compile(rf"^({prefix}{re.escape(vid)}\.path=)(.*)/include$", re.MULTILINE)
        props_content, count = path_pattern.subn(rf"\g<1>\g<2>{suffix}", props_content)
        changed += count
    return props_content, changed


def apply_include_path(props_file: Path, library_id: str, version: str, include_path: str) -> bool:
    """
    Apply a custom include path to a properties file.

    Returns:
        True if a path property was changed, False otherwise
    """
    content = props_file.read_text(encoding="utf-8")
    new_content, changed = override_include_path(content, library_id, version, include_path)
    if not changed:
        logger.warning(
            f"No libs.{library_id} path ending in /include found for {version} "
            f"in {props_file.name}; include path '{include_path}' not applied"
        )
        return False
    props_file.write_text(new_content, encoding="utf-8")
    logger.info(f"Set include path of {library_id} {version} to '{include_path}'")
    return True

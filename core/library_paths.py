"""Read, validate and override library include paths in CE properties."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .library_utils import HEADER_EXTENSIONS

logger = logging.getLogger(__name__)

CMAKE_NOT_HEADER_ONLY_NOTE = (
    "The repository has a CMakeLists.txt, so this may not be a header-only library: "
    "its headers may need to be installed through CMake"
)


def _matching_version_ids(props_content: str, library_id: str, version: str) -> list[str]:
    """Get the version ids of a library whose .version= property equals version."""
    prefix = re.escape(f"libs.{library_id}.versions.")
    version_ids = re.findall(rf"^{prefix}([^.\s]+)\.version=(.*)$", props_content, re.MULTILINE)
    return [vid for vid, ver in version_ids if ver.strip() == version]


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
    paths = []
    for vid in _matching_version_ids(props_content, library_id, version):
        path_pattern = rf"^{prefix}{re.escape(vid)}\.path=(.*)$"
        for match in re.findall(path_pattern, props_content, re.MULTILINE):
            paths.extend(p.strip() for p in match.split(":") if p.strip())
    return paths


def is_path_under(path: str, root: str) -> bool:
    """Check whether path equals root or is located below it."""
    root = root.rstrip("/")
    return path == root or path.startswith(root + "/")


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
        elif not any(f.is_file() and f.suffix in HEADER_EXTENSIONS for f in path.rglob("*")):
            problems.append(f"'{p}' contains no header files")
    return problems


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
    suffix = "" if include_path == "." else f"/{include_path}"

    changed = 0
    for vid in _matching_version_ids(props_content, library_id, version):
        path_pattern = re.compile(rf"^({prefix}{re.escape(vid)}\.path=)(.*)/include$", re.MULTILINE)
        props_content, count = path_pattern.subn(rf"\g<1>\g<2>{suffix}", props_content)
        changed += count
    return props_content, changed


def override_install_root(
    props_content: str, library_id: str, version: str, install_root: str
) -> tuple[str, int]:
    """
    Point the generated {destination}/include path of a library version at another
    destination, keeping the include/ suffix for override_include_path to replace.

    Returns:
        Tuple of (new content, number of path properties changed)
    """
    prefix = re.escape(f"libs.{library_id}.versions.")
    root = install_root.rstrip("/")

    changed = 0
    for vid in _matching_version_ids(props_content, library_id, version):
        path_pattern = re.compile(rf"^({prefix}{re.escape(vid)}\.path=).*/include$", re.MULTILINE)
        props_content, count = path_pattern.subn(
            lambda match: f"{match.group(1)}{root}/include", props_content
        )
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


def check_header_layout(analysis: dict, include_path: str | None) -> list[str]:
    """
    Check that a library whose headers are used straight from the repository has them
    where the generated properties will point.

    Only applies to libraries without package_install; the caller decides that.

    Args:
        analysis: Result of analyze_repository_structure
        include_path: Header directory override, None for the default include/

    Returns:
        Error messages, empty if the layout is fine
    """
    if include_path or analysis.get("has_include_dir"):
        return []
    errors = ["The repository has no include/ directory with headers"]
    if analysis.get("has_cmake"):
        errors.append(CMAKE_NOT_HEADER_ONLY_NOTE)
    return errors

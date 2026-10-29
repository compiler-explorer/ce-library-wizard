"""Turn C++ branch versions (trunk, main, ...) into nightly libraries.yaml entries."""
from __future__ import annotations

import copy

from ruamel.yaml.comments import CommentedMap

from .libraries_yaml import insert_sorted

NIGHTLY_CLONE = "nightlyclone"
NIGHTLY_BRANCH = "nightlybranch"
NIGHTLY_SECTION = "nightly"

# The nightly section is behind "if: nightly", so ce_install skips it unless enabled
ENABLE_NIGHTLY_ARGS = ("--enable", "nightly")

# CE names for "whatever the default branch is", rather than a branch of the repository
DEFAULT_BRANCH_VERSIONS = frozenset({"trunk", "nightly"})

# Only meaningful for an archive of a fixed ref; a nightly clone is installed at libs/<id>/<version>
RELEASE_ONLY_KEYS = frozenset({"method", "target_prefix", "targets", "untar_dir"})


def nightly_method_for_version(version: str, branches: set[str], tags: set[str]) -> str | None:
    """
    Get the infra install method for a version that tracks a branch, None for a release.

    Args:
        version: The version as given by the user
        branches: Branch names of the repository
        tags: Tag names of the repository; a version that is also a tag is a release

    Returns:
        nightlyclone for the default branch, nightlybranch for a named branch, or None
    """
    if version in DEFAULT_BRANCH_VERSIONS:
        return NIGHTLY_CLONE
    if version in branches and version not in tags:
        return NIGHTLY_BRANCH
    return None


def nightly_install_root(library_id: str, version: str) -> str:
    """Where ce_install puts a nightly C++ library: no target_prefix, unlike releases."""
    return f"/opt/compiler-explorer/libs/{library_id}/{version}"


def _target_name(target) -> str:
    return str(target.get("name")) if isinstance(target, dict) else str(target)


def move_version_to_nightly(cpp_libraries, library_id: str, version: str, method: str) -> None:
    """
    Move a version that cpp-library add wrote as a release of a top-level library into the
    library's entry in the c++ nightly section, creating that entry from the release one.

    The top-level library is removed once it has no versions left. An existing nightly entry
    keeps its own settings and only gains the version.

    Args:
        cpp_libraries: The libraries.c++ mapping of libraries.yaml
        library_id: The library identifier
        version: The version to move
        method: nightlyclone or nightlybranch
    """
    entry = cpp_libraries[library_id]
    nightly_entry = {
        key: copy.deepcopy(value) for key, value in entry.items() if key not in RELEASE_ONLY_KEYS
    }
    # cpp-library add leaves the build type out for header-only libraries
    nightly_entry.setdefault("build_type", "none")
    nightly_entry["method"] = method
    nightly_entry["targets"] = [version]

    targets = entry.get("targets") or []
    for index in reversed(range(len(targets))):
        if _target_name(targets[index]) == version:
            del targets[index]
    if not targets:
        del cpp_libraries[library_id]

    if NIGHTLY_SECTION not in cpp_libraries:
        insert_sorted(cpp_libraries, NIGHTLY_SECTION, CommentedMap())
    nightly = cpp_libraries[NIGHTLY_SECTION]

    if library_id in nightly:
        existing_targets = nightly[library_id].setdefault("targets", [])
        if version not in [_target_name(t) for t in existing_targets]:
            existing_targets.append(version)
    else:
        insert_sorted(nightly, library_id, nightly_entry)

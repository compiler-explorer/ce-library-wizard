from pathlib import Path

import pytest
from pydantic import ValidationError

from core.library_paths import (
    CMAKE_NOT_HEADER_ONLY_NOTE,
    check_header_layout,
    find_invalid_installed_paths,
    get_version_paths,
    is_path_under,
    override_include_path,
)
from core.library_utils import analyze_repository_structure
from core.models import Language, LibraryConfig

PROPS = """
libs.anyxx.name=anyxx
libs.anyxx.versions=070:061
libs.anyxx.versions.070.path=/opt/compiler-explorer/libs/anyxx/0.7.0/include
libs.anyxx.versions.070.version=0.7.0
libs.anyxx.versions.061.path=/opt/a:/opt/b
libs.anyxx.versions.061.version=0.6.1
libs.anyxx_other.versions.070.path=/elsewhere
libs.anyxx_other.versions.070.version=0.7.0
libs.zlib.versions=131
libs.zlib.packagedheaders=true
libs.zlib.versions.131.version=1.3.1
"""

DEST = "/opt/compiler-explorer/libs/anyxx/0.7.0"


def test_get_version_paths_matches_library_and_version():
    assert get_version_paths(PROPS, "anyxx", "0.7.0") == [f"{DEST}/include"]


def test_get_version_paths_splits_colon_separated():
    assert get_version_paths(PROPS, "anyxx", "0.6.1") == ["/opt/a", "/opt/b"]


def test_get_version_paths_packaged_headers_has_none():
    assert get_version_paths(PROPS, "zlib", "1.3.1") == []


def test_is_path_under_requires_component_boundary():
    assert is_path_under(DEST, DEST)
    assert is_path_under(f"{DEST}/include", DEST + "/")
    assert not is_path_under(f"{DEST}0/include", DEST)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "bit_factory").mkdir(parents=True)
    (repo / "bit_factory" / "anyxx.hpp").write_text("")
    (repo / "docs").mkdir()
    (repo / "docs" / "index.md").write_text("")
    return repo


def test_find_invalid_installed_paths(tmp_path):
    repo = _make_repo(tmp_path)
    assert find_invalid_installed_paths([str(repo), str(repo / "bit_factory")]) == []
    assert find_invalid_installed_paths([str(repo / "include")]) == [
        f"'{repo / 'include'}' does not exist"
    ]
    assert find_invalid_installed_paths([str(repo / "docs")]) == [
        f"'{repo / 'docs'}' contains no header files"
    ]


def test_override_include_path_to_root():
    new, changed = override_include_path(PROPS, "anyxx", "0.7.0", ".")
    assert changed == 1
    assert f"libs.anyxx.versions.070.path={DEST}\n" in new
    # Other versions and libraries are untouched
    assert "libs.anyxx.versions.061.path=/opt/a:/opt/b" in new
    assert "libs.anyxx_other.versions.070.path=/elsewhere" in new


def test_override_include_path_to_subdirectory():
    new, changed = override_include_path(PROPS, "anyxx", "0.7.0", "src/include")
    assert changed == 1
    assert get_version_paths(new, "anyxx", "0.7.0") == [f"{DEST}/src/include"]


def test_override_include_path_without_default_suffix_is_noop():
    new, changed = override_include_path(PROPS, "anyxx", "0.6.1", ".")
    assert changed == 0
    assert new == PROPS


def test_include_path_config_validation():
    config = LibraryConfig(
        language=Language.CPP, github_url="https://github.com/a/b", version="1", include_path="/"
    )
    assert config.include_path == "."
    with pytest.raises(ValidationError):
        LibraryConfig(
            language=Language.CPP,
            github_url="https://github.com/a/b",
            version="1",
            include_path="../x",
        )


def test_analysis_detects_missing_include_dir(tmp_path):
    repo = _make_repo(tmp_path)
    assert not analyze_repository_structure(repo)["has_include_dir"]
    (repo / "include" / "lib").mkdir(parents=True)
    (repo / "include" / "lib" / "lib.hpp").write_text("")
    assert analyze_repository_structure(repo)["has_include_dir"]


def test_check_header_layout():
    assert check_header_layout({"has_include_dir": True}, None) == []
    assert check_header_layout({"has_include_dir": False}, ".") == []
    assert check_header_layout({"has_include_dir": False}, None) == [
        "The repository has no include/ directory with headers"
    ]
    errors = check_header_layout({"has_include_dir": False, "has_cmake": True}, None)
    assert errors[-1] == CMAKE_NOT_HEADER_ONLY_NOTE

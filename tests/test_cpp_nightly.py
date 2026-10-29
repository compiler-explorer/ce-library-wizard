import subprocess
from unittest.mock import patch

import pytest

from core import models
from core.cpp_handler import CppHandler
from core.library_paths import override_install_root
from core.library_utils import build_ce_install_command
from core.models import Language, LibraryConfig, list_remote_refs
from core.nightly import NIGHTLY_BRANCH, NIGHTLY_CLONE, nightly_method_for_version

# ---------------------------------------------------------------------------
# Which versions are nightly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("version", "branches", "tags", "expected"),
    [
        ("trunk", set(), set(), NIGHTLY_CLONE),
        ("nightly", set(), set(), NIGHTLY_CLONE),
        # A repository can have a tag and a default branch both called trunk
        ("trunk", {"trunk"}, {"trunk"}, NIGHTLY_CLONE),
        ("main", {"main", "dev"}, {"1.0"}, NIGHTLY_BRANCH),
        ("dev", {"main", "dev"}, {"1.0"}, NIGHTLY_BRANCH),
        ("1.0", {"main", "1.0"}, {"1.0"}, None),
        ("1.0", {"main"}, {"1.0"}, None),
        ("2.0", {"main"}, {"1.0"}, None),
    ],
)
def test_nightly_method_for_version(version, branches, tags, expected):
    assert nightly_method_for_version(version, branches, tags) == expected


def test_list_remote_refs_splits_branches_and_tags():
    stdout = (
        "aaa\tHEAD\n"
        "bbb\trefs/heads/trunk\n"
        "ccc\trefs/heads/feature/x\n"
        "ddd\trefs/tags/trunk\n"
        "bbb\trefs/tags/trunk^{}\n"
        "eee\trefs/tags/v1.0\n"
    )
    completed = subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")
    with patch.object(models.subprocess, "run", return_value=completed):
        assert list_remote_refs("https://github.com/a/b") == (
            {"trunk", "feature/x"},
            {"trunk", "v1.0"},
        )


def test_list_remote_refs_failure_gives_no_refs():
    completed = subprocess.CompletedProcess([], 128, stdout="", stderr="not found")
    with patch.object(models.subprocess, "run", return_value=completed):
        assert list_remote_refs("https://github.com/a/b") == (set(), set())


def _normalize(language, version, branches=frozenset(), tags=frozenset()):
    config = LibraryConfig(language=language, github_url="https://github.com/a/b", version=version)
    with patch.object(
        models, "list_remote_refs", return_value=(set(branches), set(tags))
    ), patch.object(models, "check_git_tag_exists", side_effect=lambda _, tag: tag in tags):
        missing = config.normalize_versions_with_git_lookup()
    return config, missing


def test_cpp_branch_versions_need_no_tag():
    config, missing = _normalize(Language.CPP, "trunk,main,1.0", branches={"main"}, tags={"v1.0"})
    assert missing == []
    assert config.version == ["trunk", "main", "1.0"]
    assert config.nightly_methods == {"trunk": NIGHTLY_CLONE, "main": NIGHTLY_BRANCH}
    assert config.target_prefix == "v"


def test_nightly_method_follows_the_version_into_single_version_configs():
    config, _ = _normalize(Language.CPP, "trunk,1.0", tags={"1.0"})
    single = LibraryConfig(**{**config.model_dump(), "version": "trunk"})
    assert single.get_nightly_method() == NIGHTLY_CLONE
    release = LibraryConfig(**{**config.model_dump(), "version": "1.0"})
    assert release.get_nightly_method() is None


def test_only_cpp_branch_versions_become_nightly():
    config, missing = _normalize(Language.C, "trunk")
    assert missing == ["trunk"]
    assert config.nightly_methods == {}


# ---------------------------------------------------------------------------
# cpp-library add command
# ---------------------------------------------------------------------------


def _config(version, **extra):
    config = LibraryConfig(
        language=Language.CPP,
        github_url="https://github.com/a/b",
        version=version,
        target_prefix="v",
        **extra,
    )
    return config


def test_nightly_versions_get_no_target_prefix():
    config = _config("trunk", nightly_methods={"trunk": NIGHTLY_CLONE})
    command = build_ce_install_command(config, "header-only", None, {})
    assert "--target-prefix" not in command


def test_release_versions_keep_their_target_prefix():
    config = _config("1.0", nightly_methods={"trunk": NIGHTLY_CLONE})
    command = build_ce_install_command(config, "header-only", None, {})
    assert command[-2:] == ["--target-prefix", "v"]


# ---------------------------------------------------------------------------
# Moving the entry to the nightly section of libraries.yaml
# ---------------------------------------------------------------------------

LIBRARIES_YAML = """libraries:
  c++:
    # A comment that must survive.
    abc:
      check_file: README.md
      repo: owner/abc
      targets:
      - trunk
      type: github
    nightly:
      aaa:
        build_type: none
        check_file: README.md
        method: nightlyclone
        repo: owner/aaa
        targets:
        - trunk
        type: github
      zzz:
        build_type: none
        check_file: README.md
        method: nightlybranch
        repo: owner/zzz
        targets:
        - main
        type: github
    static_lib:
      build_type: cmake
      lib_type: static
      repo: owner/static_lib
      staticliblink:
      - static_lib
      target_prefix: v
      targets:
      - '1.0'
      - develop
      type: github
"""


def _move(tmp_path, library_id, version, method, content=LIBRARIES_YAML):
    yaml_path = tmp_path / "bin" / "yaml" / "libraries.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text(content)
    handler = CppHandler(tmp_path, None, setup_ce_install=False)
    assert handler.move_to_nightly(library_id, version, method)
    return yaml_path.read_text()


def test_new_header_only_library_moves_to_nightly(tmp_path):
    result = _move(tmp_path, "abc", "trunk", NIGHTLY_CLONE)
    without_release = LIBRARIES_YAML.replace(
        "    abc:\n"
        "      check_file: README.md\n"
        "      repo: owner/abc\n"
        "      targets:\n"
        "      - trunk\n"
        "      type: github\n",
        "",
    )
    assert result == without_release.replace(
        "      zzz:\n",
        "      abc:\n"
        "        build_type: none\n"
        "        check_file: README.md\n"
        "        method: nightlyclone\n"
        "        repo: owner/abc\n"
        "        targets:\n"
        "        - trunk\n"
        "        type: github\n"
        "      zzz:\n",
    )


def test_branch_of_library_with_releases_moves_without_target_prefix(tmp_path):
    result = _move(tmp_path, "static_lib", "develop", NIGHTLY_BRANCH)
    assert "      - '1.0'\n      - develop\n" not in result
    assert "      targets:\n      - '1.0'\n      type: github\n" in result
    assert (
        "      static_lib:\n"
        "        build_type: cmake\n"
        "        lib_type: static\n"
        "        method: nightlybranch\n"
        "        repo: owner/static_lib\n"
        "        staticliblink:\n"
        "        - static_lib\n"
        "        targets:\n"
        "        - develop\n"
        "        type: github\n"
        "      zzz:\n"
    ) in result
    assert "&" not in result


def test_existing_nightly_entry_keeps_its_settings(tmp_path):
    content = LIBRARIES_YAML.replace("owner/abc", "owner/zzz").replace("    abc:\n", "    zzz:\n")
    result = _move(tmp_path, "zzz", "trunk", NIGHTLY_CLONE, content)
    assert "    zzz:\n      check_file" not in result
    assert (
        "        method: nightlybranch\n"
        "        repo: owner/zzz\n"
        "        targets:\n"
        "        - main\n"
        "        - trunk\n"
    ) in result


def test_existing_nightly_version_is_not_duplicated(tmp_path):
    content = LIBRARIES_YAML.replace("owner/abc", "owner/aaa").replace("    abc:\n", "    aaa:\n")
    result = _move(tmp_path, "aaa", "trunk", NIGHTLY_CLONE, content)
    assert result == content.replace(
        "    aaa:\n"
        "      check_file: README.md\n"
        "      repo: owner/aaa\n"
        "      targets:\n"
        "      - trunk\n"
        "      type: github\n",
        "",
    )


def test_nightly_section_is_created_if_missing(tmp_path):
    content = """libraries:
  c++:
    abc:
      check_file: README.md
      repo: owner/abc
      targets:
      - trunk
      type: github
"""
    assert _move(tmp_path, "abc", "trunk", NIGHTLY_CLONE, content) == (
        "libraries:\n"
        "  c++:\n"
        "    nightly:\n"
        "      abc:\n"
        "        build_type: none\n"
        "        check_file: README.md\n"
        "        method: nightlyclone\n"
        "        repo: owner/abc\n"
        "        targets:\n"
        "        - trunk\n"
        "        type: github\n"
    )


# ---------------------------------------------------------------------------
# Properties path of a nightly version
# ---------------------------------------------------------------------------

PROPS = """libs.lib.name=lib
libs.lib.versions=100:trunk
libs.lib.versions.100.version=1.0
libs.lib.versions.100.path=/opt/compiler-explorer/libs/lib/v1.0/include
libs.lib.versions.trunk.version=trunk
libs.lib.versions.trunk.path=/opt/compiler-explorer/libs/lib/vtrunk/include
"""


def test_override_install_root_only_changes_that_version():
    content, changed = override_install_root(
        PROPS, "lib", "trunk", "/opt/compiler-explorer/libs/lib/trunk"
    )
    assert changed == 1
    assert content == PROPS.replace("lib/vtrunk/include", "lib/trunk/include")

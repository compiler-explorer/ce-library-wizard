import pytest

from core.library_utils import suggest_library_id_from_github_url
from core.models import (
    Language,
    LibraryConfig,
    extract_github_repo_info,
    normalize_github_url,
)

CLEAN = "https://github.com/Gag91/Help_Library"


@pytest.mark.parametrize(
    "given",
    [
        CLEAN,
        f"{CLEAN}/",
        f"{CLEAN}.git",
        f"{CLEAN}.git/",
        f"  {CLEAN}.git  ",
        "http://github.com/Gag91/Help_Library.git",
        "https://www.github.com/Gag91/Help_Library",
        "github.com/Gag91/Help_Library.git",
    ],
)
def test_normalize_github_url(given):
    assert normalize_github_url(given) == CLEAN


def test_normalize_keeps_other_hosts_apart_from_suffixes():
    assert normalize_github_url("https://gitlab.com/a/b.git/") == "https://gitlab.com/a/b"


def test_normalize_only_strips_a_whole_git_suffix():
    assert normalize_github_url("https://github.com/a/legit") == "https://github.com/a/legit"


@pytest.mark.parametrize("language", [Language.C, Language.CPP, Language.FORTRAN])
def test_library_config_stores_the_clean_url(language):
    config = LibraryConfig(language=language, github_url=f"{CLEAN}.git", version="1.0.0")
    assert str(config.github_url) == CLEAN


def test_repo_info_and_library_id_ignore_git_suffix():
    assert extract_github_repo_info(f"{CLEAN}.git/") == ("Gag91", "Help_Library")
    assert suggest_library_id_from_github_url(f"{CLEAN}.git") == "help_library"

import io
import urllib.error
import zipfile
from unittest.mock import MagicMock, patch

import pytest

import cli.main as cli_main
from core.go_handler import (
    AmbiguousImportPathError,
    GoModuleResolutionError,
    detect_import_path,
    fetch_module_packages,
    validate_import_path,
)
from core.models import Language, LibraryConfig

PROXY = "https://proxy.golang.org"
MODULE = "example.com/mod"
VERSION = "v1.0.0"
ZIP_URL = f"{PROXY}/{MODULE}/@v/{VERSION}.zip"


def module_zip(files: list[str], module: str = MODULE, version: str = VERSION) -> bytes:
    """Build a module zip, as the Go proxy serves it, holding the given files."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name in files:
            zf.writestr(f"{module}@{version}/{name}", "package x\n")
    return buffer.getvalue()


def serve(zips: dict[str, bytes]):
    """Patch urlopen to serve the given {url: bytes}, 404 otherwise."""

    def urlopen(url, timeout=None):
        if url in zips:
            return io.BytesIO(zips[url])
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    return patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen)


def serve_module(files: list[str]):
    return serve({ZIP_URL: module_zip(files)})


# --- fetch_module_packages ---


def test_packages_are_directories_with_non_test_go_files():
    files = [
        "go.mod",
        "a/a.go",
        "a/b/b.go",
        "onlytests/x_test.go",
        "nogo/README.md",
        "a/testdata/t.go",
        "_ignored/i.go",
        ".hidden/h.go",
    ]
    with serve_module(files):
        assert fetch_module_packages(MODULE, VERSION) == {"a", "a/b"}


def test_download_failure_raises():
    with serve({}), pytest.raises(GoModuleResolutionError, match="HTTP 404"):
        fetch_module_packages(MODULE, VERSION)


def test_network_error_raises():
    def urlopen(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        with pytest.raises(GoModuleResolutionError, match="no route to host"):
            fetch_module_packages(MODULE, VERSION)


def test_bad_zip_raises():
    with serve({ZIP_URL: b"not a zip"}), pytest.raises(GoModuleResolutionError, match="invalid"):
        fetch_module_packages(MODULE, VERSION)


# --- detect_import_path ---


def test_root_importable_needs_no_import_path():
    with serve_module(["go.mod", "root.go", "sub/sub.go", "other/other.go"]):
        assert detect_import_path(MODULE, VERSION) is None


def test_version_without_v_prefix():
    with serve_module(["root.go"]):
        assert detect_import_path(MODULE, "1.0.0") is None


def test_single_candidate_is_used():
    with serve_module(["go.mod", "only/only.go", "cmd/tool/main.go", "internal/x/x.go"]):
        assert detect_import_path(MODULE, VERSION) == f"{MODULE}/only"


def test_directory_without_its_own_package_is_not_a_candidate():
    with serve_module(["types/known/anypb/any.go", "proto/proto.go"]):
        assert detect_import_path(MODULE, VERSION) == f"{MODULE}/proto"


def test_several_candidates_raise_with_the_list():
    with serve_module(["cpu/cpu.go", "unix/unix.go", "windows/windows.go"]):
        with pytest.raises(AmbiguousImportPathError) as raised:
            detect_import_path(MODULE, VERSION)
    assert raised.value.candidates == [f"{MODULE}/cpu", f"{MODULE}/unix", f"{MODULE}/windows"]
    assert f"{MODULE}/unix" in str(raised.value)


def test_no_candidates_raises():
    with serve_module(["go.mod", "cmd/tool/main.go", "internal/x/x.go"]):
        with pytest.raises(GoModuleResolutionError, match="no package at its root"):
            detect_import_path(MODULE, VERSION)


def test_detect_download_failure_raises():
    with serve({}), pytest.raises(GoModuleResolutionError):
        detect_import_path(MODULE, VERSION)


# --- validate_import_path ---


@pytest.mark.parametrize("import_path", [f"{MODULE}/unix", f"{MODULE}/a/b", MODULE])
def test_valid_import_path(import_path):
    with serve_module(["root.go", "unix/unix.go", "a/b/b.go"]):
        validate_import_path(MODULE, VERSION, import_path)


@pytest.mark.parametrize(
    ("import_path", "files", "message"),
    [
        (f"{MODULE}/missing", ["unix/unix.go"], "not a package"),
        (f"{MODULE}/a", ["a/b/b.go"], "not a package"),
        (f"{MODULE}/unix", ["unix/unix_test.go"], "not a package"),
        (MODULE, ["unix/unix.go"], "not a package"),
        (f"{MODULE}x/unix", ["unix/unix.go"], "not inside module"),
        ("other.com/mod/unix", ["unix/unix.go"], "not inside module"),
    ],
)
def test_invalid_import_path_raises(import_path, files, message):
    with serve_module(files), pytest.raises(GoModuleResolutionError, match=message):
        validate_import_path(MODULE, VERSION, import_path)


def test_validate_download_failure_raises():
    with serve({}), pytest.raises(GoModuleResolutionError, match="Could not download"):
        validate_import_path(MODULE, VERSION, f"{MODULE}/unix")


# --- process_go_library (non-interactive) ---


class StopFlow(Exception):
    pass


def run_go_flow(files: list[str], import_path: str | None = None):
    """Run the CLI's Go flow up to cloning, with the module path already correct."""
    config = LibraryConfig(
        language=Language.GO, module=MODULE, version=VERSION, import_path=import_path
    )
    git_manager = MagicMock()
    git_manager.return_value.__enter__.return_value.clone_repositories.side_effect = StopFlow
    with (
        serve_module(files),
        patch.object(cli_main, "resolve_go_module", return_value=(MODULE, None)),
        patch.object(cli_main, "GitManager", git_manager),
    ):
        try:
            cli_main.process_go_library(config, dry_run=True, yes=True)
        except StopFlow:
            return config, True
    return config, False


def test_cli_several_candidates_stops_and_lists_them(capsys):
    _, reached_clone = run_go_flow(["cpu/cpu.go", "unix/unix.go"])
    err = capsys.readouterr().err
    assert not reached_clone
    assert f"{MODULE}/cpu" in err
    assert f"{MODULE}/unix" in err
    assert "--import-path" in err


def test_cli_single_candidate_is_used():
    config, reached_clone = run_go_flow(["unix/unix.go"])
    assert reached_clone
    assert config.import_path == f"{MODULE}/unix"


def test_cli_root_importable_has_no_import_path():
    config, reached_clone = run_go_flow(["root.go", "unix/unix.go"])
    assert reached_clone
    assert config.import_path is None


def test_cli_given_import_path_is_kept():
    config, reached_clone = run_go_flow(["cpu/cpu.go", "unix/unix.go"], f"{MODULE}/unix")
    assert reached_clone
    assert config.import_path == f"{MODULE}/unix"


def test_cli_invalid_import_path_stops(capsys):
    _, reached_clone = run_go_flow(["cpu/cpu.go", "unix/unix.go"], f"{MODULE}/nope")
    assert not reached_clone
    assert "not a package" in capsys.readouterr().err

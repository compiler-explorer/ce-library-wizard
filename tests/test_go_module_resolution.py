import io
import urllib.error
from unittest.mock import patch

import pytest

from core.go_handler import (
    GoModuleResolutionError,
    escape_module_path,
    parse_go_mod_module,
    resolve_go_module,
)

PROXY = "https://proxy.golang.org"


def fake_proxy(mod_files: dict[str, str]):
    """Build a urlopen replacement serving the given {url: go.mod text}, 404 otherwise."""
    requested: list[str] = []

    def urlopen(url, timeout=None):
        requested.append(url)
        if url in mod_files:
            return io.BytesIO(mod_files[url].encode())
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    urlopen.requested = requested
    return urlopen


def resolve_with(mod_files: dict[str, str], module_path: str, version: str):
    urlopen = fake_proxy(mod_files)
    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        return resolve_go_module(module_path, version), urlopen.requested


# --- escape_module_path ---


@pytest.mark.parametrize(
    ("module_path", "expected"),
    [
        ("github.com/google/uuid", "github.com/google/uuid"),
        ("github.com/BurntSushi/toml", "github.com/!burnt!sushi/toml"),
        ("github.com/Azure/azure-sdk-for-go", "github.com/!azure/azure-sdk-for-go"),
    ],
)
def test_escape_module_path(module_path, expected):
    assert escape_module_path(module_path) == expected


# --- parse_go_mod_module ---


@pytest.mark.parametrize(
    ("go_mod", "expected"),
    [
        ("module go.uber.org/zap\n\ngo 1.19\n", "go.uber.org/zap"),
        ('// comment\nmodule "golang.org/x/sys"\n', "golang.org/x/sys"),
        ("module example.com/mod // trailing comment\n", "example.com/mod"),
        ("go 1.21\n", None),
    ],
)
def test_parse_go_mod_module(go_mod, expected):
    assert parse_go_mod_module(go_mod) == expected


# --- resolve_go_module ---


def test_correct_module_is_unchanged():
    files = {f"{PROXY}/github.com/google/go-cmp/@v/v0.7.0.mod": "module github.com/google/go-cmp\n"}
    (module, import_path), requested = resolve_with(files, "github.com/google/go-cmp", "v0.7.0")
    assert (module, import_path) == ("github.com/google/go-cmp", None)
    assert requested == [f"{PROXY}/github.com/google/go-cmp/@v/v0.7.0.mod"]


def test_version_without_v_prefix():
    files = {f"{PROXY}/github.com/google/go-cmp/@v/v0.7.0.mod": "module github.com/google/go-cmp\n"}
    (module, _), _ = resolve_with(files, "github.com/google/go-cmp", "0.7.0")
    assert module == "github.com/google/go-cmp"


def test_repo_path_resolves_to_declared_module():
    files = {
        f"{PROXY}/github.com/uber-go/zap/@v/v1.28.0.mod": "module go.uber.org/zap\n\ngo 1.19\n",
        f"{PROXY}/go.uber.org/zap/@v/v1.28.0.mod": "module go.uber.org/zap\n\ngo 1.19\n",
    }
    (module, import_path), _ = resolve_with(files, "github.com/uber-go/zap", "v1.28.0")
    assert (module, import_path) == ("go.uber.org/zap", None)


def test_repo_subpackage_path_resolves_to_declared_module_subpackage():
    files = {
        f"{PROXY}/github.com/uber-go/zap/@v/v1.28.0.mod": "module go.uber.org/zap\n",
        f"{PROXY}/go.uber.org/zap/@v/v1.28.0.mod": "module go.uber.org/zap\n",
    }
    (module, import_path), _ = resolve_with(files, "github.com/uber-go/zap/zapcore", "v1.28.0")
    assert (module, import_path) == ("go.uber.org/zap", "go.uber.org/zap/zapcore")


def test_subpackage_path_walks_up_to_module():
    files = {
        f"{PROXY}/google.golang.org/protobuf/@v/v1.36.0.mod": "module google.golang.org/protobuf\n"
    }
    (module, import_path), _ = resolve_with(files, "google.golang.org/protobuf/proto", "v1.36.0")
    assert (module, import_path) == (
        "google.golang.org/protobuf",
        "google.golang.org/protobuf/proto",
    )


@pytest.mark.parametrize(
    "entered",
    [
        "https://github.com/google/go-cmp",
        "http://github.com/google/go-cmp/",
        " github.com/google/go-cmp ",
    ],
)
def test_url_scheme_is_stripped(entered):
    files = {f"{PROXY}/github.com/google/go-cmp/@v/v0.7.0.mod": "module github.com/google/go-cmp\n"}
    (module, import_path), _ = resolve_with(files, entered, "v0.7.0")
    assert (module, import_path) == ("github.com/google/go-cmp", None)


def test_uppercase_letters_are_escaped_in_proxy_url():
    files = {
        f"{PROXY}/github.com/!burnt!sushi/toml/@v/v1.4.0.mod": "module github.com/BurntSushi/toml\n"
    }
    (module, import_path), requested = resolve_with(files, "github.com/BurntSushi/toml", "v1.4.0")
    assert (module, import_path) == ("github.com/BurntSushi/toml", None)
    assert requested == [f"{PROXY}/github.com/!burnt!sushi/toml/@v/v1.4.0.mod"]


def test_unknown_module_raises():
    with pytest.raises(GoModuleResolutionError, match="go.googlesource.com/sys"):
        resolve_with({}, "https://go.googlesource.com/sys", "v0.49.0")


def test_declared_module_not_served_raises():
    files = {f"{PROXY}/github.com/someone/fork/@v/v1.0.0.mod": "module example.com/upstream\n"}
    with pytest.raises(GoModuleResolutionError, match="example.com/upstream"):
        resolve_with(files, "github.com/someone/fork", "v1.0.0")


def test_network_error_raises():
    def urlopen(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        with pytest.raises(GoModuleResolutionError, match="no route to host"):
            resolve_go_module("github.com/google/go-cmp", "v0.7.0")

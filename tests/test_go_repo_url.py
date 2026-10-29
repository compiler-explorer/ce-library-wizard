import io
import urllib.error
from unittest.mock import patch

import pytest

from core.go_handler import module_repo_url, parse_go_get_meta


def meta(name: str, *fields: str) -> str:
    return f'<meta name="{name}" content="{" ".join(fields)}">\n'


def go_source(prefix: str, home: str, tree: str) -> str:
    return meta("go-source", prefix, home, f"{tree}{{/dir}}", f"{tree}{{/dir}}/{{file}}#L{{line}}")


ZAP_PAGE = (
    "<!DOCTYPE html><html><head>\n"
    + meta("go-import", "go.uber.org/zap", "git", "https://github.com/uber-go/zap")
    + go_source(
        "go.uber.org/zap",
        "https://github.com/uber-go/zap",
        "https://github.com/uber-go/zap/tree/master",
    )
    + "</head></html>"
)

PROTOBUF_PAGE = meta(
    "go-import", "google.golang.org/protobuf", "git", "https://go.googlesource.com/protobuf"
) + go_source(
    "google.golang.org/protobuf",
    "https://github.com/protocolbuffers/protobuf-go",
    "https://github.com/protocolbuffers/protobuf-go/tree/master",
)

SYS_PAGE = meta("go-import", "golang.org/x/sys", "git", "https://go.googlesource.com/sys")

YAML_PAGE = meta("go-import", "gopkg.in/yaml.v3", "git", "https://gopkg.in/yaml.v3") + go_source(
    "gopkg.in/yaml.v3", "_", "https://github.com/go-yaml/yaml/tree/v3.0.1"
)


# --- parse_go_get_meta ---


@pytest.mark.parametrize(
    ("html", "module_path", "expected"),
    [
        (ZAP_PAGE, "go.uber.org/zap", "https://github.com/uber-go/zap"),
        (
            PROTOBUF_PAGE,
            "google.golang.org/protobuf",
            "https://github.com/protocolbuffers/protobuf-go",
        ),
        (SYS_PAGE, "golang.org/x/sys", "https://go.googlesource.com/sys"),
        # go-source home "_" means none: fall back to go-import
        (YAML_PAGE, "gopkg.in/yaml.v3", "https://gopkg.in/yaml.v3"),
        # a module inside a repository uses the repository's tags
        (SYS_PAGE, "golang.org/x/sys/unix", "https://go.googlesource.com/sys"),
        (
            '<meta name="go-import" content="example.com/mod git https://git.example.com/mod.git/">',
            "example.com/mod",
            "https://git.example.com/mod",
        ),
        (
            "<meta content='example.com/mod git https://git.example.com/mod' name='go-import'>",
            "example.com/mod",
            "https://git.example.com/mod",
        ),
    ],
)
def test_parse_go_get_meta(html, module_path, expected):
    assert parse_go_get_meta(html, module_path) == expected


@pytest.mark.parametrize(
    ("html", "module_path"),
    [
        ("<html><head><title>No tags</title></head></html>", "example.com/mod"),
        # tags for another module, or a sibling sharing a name prefix
        (SYS_PAGE, "golang.org/x/net"),
        (SYS_PAGE, "golang.org/x/sysfoo"),
        # a GOPROXY-style "mod" entry has no repository
        (
            '<meta name="go-import" content="example.com/mod mod https://proxy.example.com">',
            "example.com/mod",
        ),
    ],
)
def test_parse_go_get_meta_finds_nothing(html, module_path):
    assert parse_go_get_meta(html, module_path) is None


# --- module_repo_url ---


def test_github_module_needs_no_lookup():
    with patch("core.go_handler.urllib.request.urlopen") as urlopen:
        assert module_repo_url("github.com/google/uuid") == "https://github.com/google/uuid"
    urlopen.assert_not_called()


def test_vanity_module_is_looked_up():
    requested = []

    def urlopen(url, timeout=None):
        requested.append(url)
        return io.BytesIO(ZAP_PAGE.encode())

    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        assert module_repo_url("go.uber.org/zap") == "https://github.com/uber-go/zap"
    assert requested == ["https://go.uber.org/zap?go-get=1"]


def test_lookup_failure_gives_no_url():
    def urlopen(url, timeout=None):
        raise urllib.error.URLError("no route to host")

    with patch("core.go_handler.urllib.request.urlopen", side_effect=urlopen):
        assert module_repo_url("go.uber.org/zap") is None


def test_page_without_tags_gives_no_url():
    with patch("core.go_handler.urllib.request.urlopen", return_value=io.BytesIO(b"<html></html>")):
        assert module_repo_url("example.com/mod") is None

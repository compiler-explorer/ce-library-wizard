import pytest

from core.go_handler import (
    GoHandler,
    display_name_from_module,
    normalize_module_input,
    parse_module_directive,
)
from core.models import Language, LibraryConfig


@pytest.mark.parametrize(
    ("module_path", "expected"),
    [
        ("github.com/google/uuid", "google/uuid"),
        ("github.com/pkg/errors", "pkg/errors"),
        ("google.golang.org/protobuf", "protobuf"),
        ("go.uber.org/zap", "zap"),
        ("golang.org/x/sys", "x/sys"),
        ("github.com/google/uuid/", "google/uuid"),
        ("github.com/go-yaml/yaml/v3", "go-yaml/yaml"),
        ("go.uber.org/zap/v2", "zap"),
        ("gopkg.in/yaml.v3", "yaml.v3"),
        ("github.com/aws/aws-sdk-go-v2/service/s3", "service/s3"),
        ("example.com/mod", "mod"),
        ("mymodule", "mymodule"),
        ("https://go.googlesource.com/sys", "sys"),
        ("https://github.com/google/uuid", "google/uuid"),
    ],
)
def test_display_name_from_module(module_path, expected):
    assert display_name_from_module(module_path) == expected


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("github.com/google/uuid", "github.com/google/uuid"),
        ("https://github.com/uber-go/zap", "github.com/uber-go/zap"),
        ("https://github.com/uber-go/zap.git", "github.com/uber-go/zap"),
        ("https://go.googlesource.com/sys", "golang.org/x/sys"),
        ("https://go.googlesource.com/sys/", "golang.org/x/sys"),
        ("go.googlesource.com/net/http2", "golang.org/x/net/http2"),
    ],
)
def test_normalize_module_input(given, expected):
    assert normalize_module_input(given) == expected


@pytest.mark.parametrize(
    ("go_mod", "expected"),
    [
        ("module go.uber.org/zap\n\ngo 1.19\n", "go.uber.org/zap"),
        ('// comment\nmodule "example.com/quoted"\n', "example.com/quoted"),
        ("go 1.19\n", None),
    ],
)
def test_parse_module_directive(go_mod, expected):
    assert parse_module_directive(go_mod) == expected


LIBRARIES_YAML = """libraries:
  c++:
    # A comment that must survive.
    zlib:
      type: github
      description: "keys deliberately unsorted"
      targets:
      - 1.3.1
  go:
    errors:
      build_type: gomod
      module: github.com/pkg/errors
      targets:
      - v0.9.1
      type: gomod
    uuid:
      build_type: gomod
      module: github.com/google/uuid
      targets:
      - v1.6.0
      type: gomod
"""


def _add(tmp_path, **config):
    yaml_path = tmp_path / "bin" / "yaml" / "libraries.yaml"
    yaml_path.parent.mkdir(parents=True)
    yaml_path.write_text(LIBRARIES_YAML)
    handler = GoHandler(tmp_path, None)
    assert handler.add_library(LibraryConfig(language=Language.GO, **config))
    return yaml_path.read_text()


def test_adding_a_version_only_adds_that_line(tmp_path):
    result = _add(tmp_path, module="github.com/pkg/errors", version="v0.9.2", library_id="errors")
    assert result == LIBRARIES_YAML.replace("      - v0.9.1\n", "      - v0.9.1\n      - v0.9.2\n")


def test_new_library_goes_in_sorted_position(tmp_path):
    result = _add(tmp_path, module="go.uber.org/zap", version="v1.28.0", library_id="sys_zap")
    assert result == LIBRARIES_YAML.replace(
        "    uuid:\n",
        "    sys_zap:\n"
        "      build_type: gomod\n"
        "      module: go.uber.org/zap\n"
        "      targets:\n"
        "      - v1.28.0\n"
        "      type: gomod\n"
        "    uuid:\n",
    )

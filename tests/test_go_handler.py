import pytest

from core.go_handler import display_name_from_module


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

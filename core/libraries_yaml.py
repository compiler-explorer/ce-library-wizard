"""Edit infra's libraries.yaml the way infra's own LibraryYaml does."""
from __future__ import annotations

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


def round_trip_yaml() -> YAML:
    """
    A YAML loader/dumper that keeps libraries.yaml's comments, key order and quoting, so
    adding a library only changes the lines it adds. Matches infra's LibraryYaml.
    """
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=2, offset=0)
    return yaml


def insert_sorted(mapping, key: str, value) -> None:
    """Add a new key to a libraries.yaml mapping, before the first key that sorts after it."""
    entry = CommentedMap(sorted(value.items())) if isinstance(value, dict) else value
    position = next((i for i, existing in enumerate(mapping) if str(existing) > key), len(mapping))
    mapping.insert(position, key, entry)

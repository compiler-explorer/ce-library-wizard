import pytest

from core.constants import FORTRAN_PROPERTIES_PATH, GO_PROPERTIES_PATH
from core.file_modifications import insert_library_properties
from core.fortran_handler import FortranHandler
from core.go_handler import GoHandler
from core.models import Language, LibraryConfig

EXISTING_LIBS = "libs=errors\n\nlibs.errors.name=errors\nlibs.errors.versions=v091\n"
TOOLS_SECTION = (
    "#################################\n"
    "#################################\n"
    "# Installed tools\n"
    "\n"
    "tools=readelf\n"
)
WITH_TOOLS = EXISTING_LIBS + "\n" + TOOLS_SECTION
NEW_PROPS = ["libs.foo.name=foo", "libs.foo.versions=v1"]
NEW_BLOCK = "libs.foo.name=foo\nlibs.foo.versions=v1\n"


def test_inserts_before_installed_tools_with_one_blank_line_each_side():
    result = insert_library_properties(WITH_TOOLS, NEW_PROPS)
    assert result == EXISTING_LIBS + "\n" + NEW_BLOCK + "\n" + TOOLS_SECTION


def test_collapses_extra_blank_lines_before_installed_tools():
    content = EXISTING_LIBS + "\n\n\n" + TOOLS_SECTION
    result = insert_library_properties(content, NEW_PROPS)
    assert result == EXISTING_LIBS + "\n" + NEW_BLOCK + "\n" + TOOLS_SECTION


@pytest.mark.parametrize("trailing", ["", "\n", "\n\n"])
def test_appends_at_end_without_installed_tools(trailing):
    content = EXISTING_LIBS.rstrip("\n") + trailing
    result = insert_library_properties(content, NEW_PROPS)
    assert result == EXISTING_LIBS + "\n" + NEW_BLOCK


def test_appends_to_empty_file():
    assert insert_library_properties("", NEW_PROPS) == NEW_BLOCK


def _write_props(tmp_path, relative_path, content):
    props_file = tmp_path / relative_path
    props_file.parent.mkdir(parents=True)
    props_file.write_text(content, encoding="utf-8")
    return props_file


def test_go_handler_leaves_one_blank_line_before_installed_tools(tmp_path):
    props_file = _write_props(tmp_path, GO_PROPERTIES_PATH, WITH_TOOLS)
    handler = GoHandler(tmp_path, main_path=tmp_path, setup_ce_install=False)
    config = LibraryConfig(language=Language.GO, module="github.com/google/uuid", version="1.6.0")

    assert handler.update_go_properties("uuid", config)

    expected_block = (
        "libs.uuid.name=google/uuid\n"
        "libs.uuid.url=https://github.com/google/uuid\n"
        "libs.uuid.lookupname=go_uuid\n"
        "libs.uuid.packagedheaders=true\n"
        "libs.uuid.versions=v160\n"
        "libs.uuid.versions.v160.version=v1.6.0\n"
    )
    assert props_file.read_text() == EXISTING_LIBS + "\n" + expected_block + "\n" + TOOLS_SECTION


def test_fortran_handler_leaves_one_blank_line_before_installed_tools(tmp_path):
    props_file = _write_props(tmp_path, FORTRAN_PROPERTIES_PATH, WITH_TOOLS)
    handler = FortranHandler(tmp_path, main_path=tmp_path, setup_ce_install=False)
    config = LibraryConfig(
        language=Language.FORTRAN, github_url="https://github.com/example/foo", version="1.0.0"
    )

    assert handler.update_fortran_properties("foo", config)

    expected_block = (
        "libs.foo.name=foo\n"
        "libs.foo.url=https://github.com/example/foo\n"
        "libs.foo.staticliblink=foo\n"
        "libs.foo.versions=100\n"
        "libs.foo.packagedheaders=true\n"
        "libs.foo.versions.100.version=1.0.0\n"
    )
    assert props_file.read_text() == EXISTING_LIBS + "\n" + expected_block + "\n" + TOOLS_SECTION

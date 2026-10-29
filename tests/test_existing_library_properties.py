from core.constants import FORTRAN_PROPERTIES_PATH, GO_PROPERTIES_PATH
from core.file_modifications import add_version_to_existing_library
from core.fortran_handler import FortranHandler
from core.go_handler import GoHandler
from core.models import Language, LibraryConfig

FORTRAN_PROPS = (
    "libs=http_client:json_fortran\n"
    "\n"
    "libs.http_client.name=http-client\n"
    "libs.http_client.url=https://github.com/fortran-lang/http-client\n"
    "libs.http_client.staticliblink=http_client\n"
    "libs.http_client.versions=010\n"
    "libs.http_client.packagedheaders=true\n"
    "libs.http_client.versions.010.version=0.1.0\n"
    "\n"
    "libs.json_fortran.name=json-fortran\n"
    "libs.json_fortran.versions=900\n"
    "libs.json_fortran.versions.900.version=9.0.0\n"
)

GO_PROPS = (
    "libs=zap\n"
    "\n"
    "libs.zap.name=zap\n"
    "libs.zap.lookupname=go_zap\n"
    "libs.zap.packagedheaders=true\n"
    "libs.zap.versions=v1100\n"
    "libs.zap.versions.v1100.version=v1.10.0\n"
)


# --- add_version_to_existing_library ---


def test_appends_version_to_existing_block():
    result = add_version_to_existing_library(
        FORTRAN_PROPS, "http_client", "020", ["libs.http_client.versions.020.version=0.2.0"]
    )
    assert result == FORTRAN_PROPS.replace(
        "libs.http_client.versions=010\n", "libs.http_client.versions=010:020\n"
    ).replace(
        "libs.http_client.versions.010.version=0.1.0\n",
        "libs.http_client.versions.010.version=0.1.0\n"
        "libs.http_client.versions.020.version=0.2.0\n",
    )


def test_unknown_library_returns_none():
    assert add_version_to_existing_library(FORTRAN_PROPS, "foo", "100", ["x"]) is None


def test_library_id_prefix_is_not_a_match():
    assert add_version_to_existing_library(FORTRAN_PROPS, "http", "100", ["x"]) is None


def test_listed_version_leaves_content_unchanged():
    assert add_version_to_existing_library(FORTRAN_PROPS, "http_client", "010", ["x"]) == (
        FORTRAN_PROPS
    )


def test_version_that_is_a_substring_of_a_listed_one_is_added():
    result = add_version_to_existing_library(
        GO_PROPS, "zap", "v110", ["libs.zap.versions.v110.version=v1.1.0"]
    )
    assert "libs.zap.versions=v1100:v110\n" in result
    assert result.endswith(
        "libs.zap.versions.v1100.version=v1.10.0\nlibs.zap.versions.v110.version=v1.1.0\n"
    )


def test_empty_versions_list():
    result = add_version_to_existing_library(
        "libs.foo.name=foo\nlibs.foo.versions=\n", "foo", "100", ["libs.foo.versions.100.version=1"]
    )
    assert result == ("libs.foo.name=foo\nlibs.foo.versions=100\nlibs.foo.versions.100.version=1\n")


# --- handlers ---


def _write_props(tmp_path, relative_path, content):
    props_file = tmp_path / relative_path
    props_file.parent.mkdir(parents=True)
    props_file.write_text(content, encoding="utf-8")
    return props_file


def test_fortran_handler_adds_version_to_existing_library(tmp_path):
    props_file = _write_props(tmp_path, FORTRAN_PROPERTIES_PATH, FORTRAN_PROPS)
    handler = FortranHandler(tmp_path, main_path=tmp_path, setup_ce_install=False)
    config = LibraryConfig(
        language=Language.FORTRAN,
        github_url="https://github.com/fortran-lang/http-client",
        version="0.2.0",
    )
    assert handler.update_fortran_properties("http_client", config)

    content = props_file.read_text()
    assert content.count("libs.http_client.name=") == 1
    assert "libs.http_client.name=http-client\n" in content
    assert "libs.http_client.versions=010:020\n" in content
    assert (
        "libs.http_client.versions.010.version=0.1.0\n"
        "libs.http_client.versions.020.version=0.2.0\n"
    ) in content


def test_fortran_handler_skips_listed_version(tmp_path):
    props_file = _write_props(tmp_path, FORTRAN_PROPERTIES_PATH, FORTRAN_PROPS)
    handler = FortranHandler(tmp_path, main_path=tmp_path, setup_ce_install=False)
    config = LibraryConfig(
        language=Language.FORTRAN,
        github_url="https://github.com/fortran-lang/http-client",
        version="0.1.0",
    )
    assert handler.update_fortran_properties("http_client", config)
    assert props_file.read_text() == FORTRAN_PROPS


def test_go_handler_adds_version_that_is_a_substring_of_a_listed_one(tmp_path):
    props_file = _write_props(tmp_path, GO_PROPERTIES_PATH, GO_PROPS)
    handler = GoHandler(tmp_path, main_path=tmp_path, setup_ce_install=False)
    config = LibraryConfig(language=Language.GO, module="github.com/uber-go/zap", version="1.1.0")
    assert handler.update_go_properties("zap", config)

    content = props_file.read_text()
    assert content.count("libs.zap.name=") == 1
    assert "libs.zap.versions=v1100:v110\n" in content
    assert content.endswith("libs.zap.versions.v110.version=v1.1.0\n")

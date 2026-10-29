"""Handle Go library additions to Compiler Explorer."""
from __future__ import annotations

import io
import logging
import re
import urllib.request
import zipfile
from pathlib import Path

from ruamel.yaml import YAML

from .build_tester import (
    BuildTestResult,
    check_go_build_test_available,
    run_go_build_test,
)
from .constants import GO_PROPERTIES_PATH, LIBRARIES_YAML_PATH, MAIN_REPO_PATH_REQUIRED
from .file_modifications import add_version_to_existing_library, insert_library_properties
from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .models import LibraryConfig

logger = logging.getLogger(__name__)

GO_PROXY_URL = "https://proxy.golang.org"


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
    entry = {k: value[k] for k in sorted(value)} if isinstance(value, dict) else value
    position = next((i for i, existing in enumerate(mapping) if str(existing) > key), len(mapping))
    mapping.insert(position, key, entry)


def suggest_library_id_from_module(module_path: str) -> str:
    """
    Suggest a library ID from a Go module path.

    Examples:
        github.com/google/uuid -> uuid
        google.golang.org/protobuf -> protobuf
        github.com/pkg/errors -> errors
    """
    # Use the last component of the module path
    parts = module_path.rstrip("/").split("/")
    name = parts[-1] if parts else "unknown"

    # Clean up the name: lowercase, replace hyphens with underscores
    name = name.lower()
    name = re.sub(r"[^a-z0-9_]", "_", name)
    name = re.sub(r"_+", "_", name)
    name = name.strip("_")

    if not name or not name[0].isalpha():
        name = "lib_" + name

    return name


def display_name_from_module(module_path: str) -> str:
    """
    Derive a properties display name from a Go module path.

    Takes the last two path components, dropping the first of them when it is a
    domain, and ignores a trailing major-version component.

    Examples:
        github.com/google/uuid -> google/uuid
        google.golang.org/protobuf -> protobuf
        golang.org/x/sys -> x/sys
        github.com/go-yaml/yaml/v3 -> go-yaml/yaml
        gopkg.in/yaml.v3 -> yaml.v3
    """
    path = module_path.split("://", 1)[-1]
    parts = [part for part in path.split("/") if part]
    if len(parts) > 1 and re.fullmatch(r"v\d+", parts[-1]):
        parts = parts[:-1]
    if not parts:
        return module_path

    tail = parts[-2:]
    if len(tail) == 2 and "." in tail[0]:
        tail = tail[1:]
    return "/".join(tail)


def module_to_github_url(module_path: str) -> str | None:
    """
    Derive a GitHub URL from a Go module path if possible.

    Examples:
        github.com/google/uuid -> https://github.com/google/uuid
        google.golang.org/protobuf -> (not derivable, returns None)
    """
    if module_path.startswith("github.com/"):
        # Direct GitHub module - extract owner/repo (first two path components)
        parts = module_path.split("/")
        if len(parts) >= 3:
            return f"https://github.com/{parts[1]}/{parts[2]}"
    return None


def parse_go_get_meta(html: str, module_path: str) -> str | None:
    """
    Pick the repository web page from a `?go-get=1` page's go-source and go-import meta tags.

    go-source's home URL is preferred, as it is the browsable page: for google.golang.org/protobuf,
    go-import points at go.googlesource.com but go-source at github.com/protocolbuffers/protobuf-go.
    Only tags whose import prefix covers module_path are used.
    """

    def covers(prefix: str) -> bool:
        return module_path == prefix or module_path.startswith(f"{prefix}/")

    tags: dict[str, list[list[str]]] = {"go-source": [], "go-import": []}
    for tag in re.findall(r"<meta\s[^>]*>", html, re.IGNORECASE):
        name = re.search(r"""name\s*=\s*["']([^"']+)["']""", tag, re.IGNORECASE)
        content = re.search(r"""content\s*=\s*["']([^"']+)["']""", tag, re.IGNORECASE)
        if name and content and name.group(1) in tags:
            fields = content.group(1).split()
            if len(fields) >= 2 and covers(fields[0]):
                tags[name.group(1)].append(fields)

    for fields in tags["go-source"]:
        if fields[1].startswith(("https://", "http://")):
            return fields[1].rstrip("/")
    for fields in tags["go-import"]:
        if (
            len(fields) >= 3
            and fields[1] != "mod"
            and fields[2].startswith(("https://", "http://"))
        ):
            return re.sub(r"\.git$", "", fields[2].rstrip("/"))
    return None


def module_repo_url(module_path: str) -> str | None:
    """
    The web page of a Go module's repository, for the properties `url=`.

    github.com modules are derived from the path. Others are looked up the way `go get` does,
    from the meta tags at https://<module>?go-get=1 (go.uber.org/zap -> github.com/uber-go/zap).
    """
    github_url = module_to_github_url(module_path)
    if github_url:
        return github_url

    try:
        with urllib.request.urlopen(f"https://{module_path}?go-get=1", timeout=10) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"Could not look up the repository of {module_path}: {e}")
        return None

    url = parse_go_get_meta(html, module_path)
    if not url:
        logger.warning(f"No repository URL found for {module_path}; leaving url= out")
    return url


class GoModuleResolutionError(ValueError):
    """Raised when the Go module, or the package to build from it, cannot be resolved."""


def escape_module_path(module_path: str) -> str:
    """Escape a module path for the Go proxy: each uppercase letter becomes '!' + lowercase."""
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module_path)


def normalize_module_input(module_path: str) -> str:
    """
    Turn what a user is likely to paste (a repository URL) into a Go module path.

    The golang.org/x repositories are hosted on go.googlesource.com, but their module
    paths are golang.org/x/<name>.
    """
    path = module_path.strip()
    path = re.sub(r"^[a-z]+://", "", path).rstrip("/")
    path = re.sub(r"\.git$", "", path)
    googlesource = re.match(r"^go\.googlesource\.com/([^/]+)(/.*)?$", path)
    if googlesource:
        path = f"golang.org/x/{googlesource.group(1)}{googlesource.group(2) or ''}"
    return path


def parse_module_directive(go_mod: str) -> str | None:
    """Return the path from a go.mod file's `module` directive."""
    match = re.search(r"^module\s+\"?([^\s\"]+)\"?", go_mod, re.MULTILINE)
    return match.group(1) if match else None


def fetch_go_module_path(module_path: str, version: str) -> tuple[str | None, str | None]:
    """
    Fetch the .mod file the Go proxy serves for module_path@version and return
    the module path it declares.

    Returns:
        Tuple of (declared_module_path, error_message); exactly one is None.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    proxy_url = f"{GO_PROXY_URL}/{escape_module_path(module_path)}/@v/{version}.mod"
    try:
        with urllib.request.urlopen(proxy_url, timeout=10) as response:
            go_mod = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        if e.code in (404, 410):
            return None, f"Go module proxy has no module {module_path} at version {version}"
        return None, f"Error checking Go module proxy: HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError) as e:
        return None, f"Error connecting to Go module proxy: {e}"

    declared = parse_module_directive(go_mod)
    if not declared:
        return None, f"No module line in the go.mod served for {module_path}@{version}"
    return declared, None


def resolve_go_module(module_path: str, version: str) -> tuple[str, str | None]:
    """
    Resolve the real Go module path for what the user entered.

    Handles a URL (https://github.com/google/uuid), a subpackage path
    (google.golang.org/protobuf/proto) and a repository path whose go.mod declares
    a different module (github.com/uber-go/zap declares go.uber.org/zap). Walks up
    the path until the Go proxy serves a .mod file, then uses its `module` line.

    Args:
        module_path: Module path, subpackage path or URL as entered
        version: Version to check against

    Returns:
        Tuple of (actual_module_path, import_path_or_none).
        If the input was the module root, import_path is None.
        If the input was a subpackage, import_path is that subpackage under the real module.

    Raises:
        GoModuleResolutionError: if no module is found, or the declared module
        is not served by the proxy under its own path.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    original = normalize_module_input(module_path)
    parts = original.split("/")
    first_error = None

    # Need at least 2 components for a valid module (host/path)
    while len(parts) >= 2:
        candidate = "/".join(parts)
        declared, error = fetch_go_module_path(candidate, version)
        if declared:
            break
        first_error = first_error or error
        parts = parts[:-1]
    else:
        raise GoModuleResolutionError(
            f"{first_error}. Use the path from the `module` line of the library's go.mod."
        )

    if declared != candidate:
        served, _ = fetch_go_module_path(declared, version)
        if served != declared:
            raise GoModuleResolutionError(
                f"{candidate} declares its module path as {declared}, but the Go module "
                f"proxy does not serve {declared} at version {version}"
            )
        logger.info(f"{candidate} declares its module path as {declared}")

    subpackage = original[len(candidate) :]
    import_path = f"{declared}{subpackage}" if subpackage else None
    if declared != original:
        logger.info(f"Resolved module: {original} -> module={declared}, import_path={import_path}")
    return declared, import_path


# Top-level directories that are not offered as the package to build
NON_LIBRARY_DIRS = frozenset(
    {
        "internal",
        "testdata",
        "vendor",
        "cmd",
        "example",
        "examples",
        "tools",
        "hack",
        "scripts",
        "doc",
        "docs",
        "bench",
        "benchmarks",
        "test",
        "testing",
        "testutil",
    }
)


class AmbiguousImportPathError(GoModuleResolutionError):
    """Raised when a module's root has no package and several packages could be built instead."""

    def __init__(self, module_path: str, version: str, packages: set[str], candidates: list[str]):
        self.module_path = module_path
        self.version = version
        self.packages = packages
        self.candidates = candidates
        listing = "\n".join(f"  {candidate}" for candidate in candidates)
        super().__init__(
            f"{module_path}@{version} has no package at its root, and there are several "
            f"packages to choose from:\n{listing}"
        )


def _is_go_tool_ignored(directory: str) -> bool:
    """Whether the go tool ignores this directory: testdata, or a name starting with . or _."""
    return any(
        part == "testdata" or part.startswith((".", "_")) for part in directory.split("/") if part
    )


def fetch_module_packages(module_path: str, version: str) -> set[str]:
    """
    List the packages in a Go module, from the module zip the Go proxy serves.

    Returns:
        The directories, relative to the module root, that hold non-test .go files.
        The root itself is "".

    Raises:
        GoModuleResolutionError: if the zip cannot be downloaded or read.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    zip_url = f"{GO_PROXY_URL}/{escape_module_path(module_path)}/@v/{version}.zip"
    logger.info(f"Checking module structure from {zip_url}")

    try:
        with urllib.request.urlopen(zip_url, timeout=30) as response:
            zip_data = io.BytesIO(response.read())
    except urllib.error.HTTPError as e:
        raise GoModuleResolutionError(
            f"Could not download {module_path}@{version} from the Go module proxy: HTTP {e.code}"
        ) from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise GoModuleResolutionError(
            f"Could not download {module_path}@{version} from the Go module proxy: {e}"
        ) from e

    # Paths in the zip look like module@version/dir/file.go
    prefix = f"{module_path}@{version}/"
    packages: set[str] = set()
    try:
        with zipfile.ZipFile(zip_data) as zf:
            for name in zf.namelist():
                if not name.startswith(prefix):
                    continue
                directory, _, filename = name[len(prefix) :].rpartition("/")
                if not filename.endswith(".go") or filename.endswith("_test.go"):
                    continue
                if _is_go_tool_ignored(directory):
                    continue
                packages.add(directory)
    except zipfile.BadZipFile as e:
        raise GoModuleResolutionError(
            f"The Go module proxy served an invalid zip for {module_path}@{version}"
        ) from e

    return packages


def import_path_candidates(module_path: str, packages: set[str]) -> list[str]:
    """The import paths of the module's top-level packages that could be built in its place."""
    return sorted(
        f"{module_path}/{package}"
        for package in packages
        if package and "/" not in package and package not in NON_LIBRARY_DIRS
    )


def is_package_in_module(module_path: str, import_path: str, packages: set[str]) -> bool:
    """Whether import_path names one of the packages (as fetch_module_packages lists them)."""
    if import_path == module_path:
        return "" in packages
    if not import_path.startswith(f"{module_path}/"):
        return False
    return import_path[len(module_path) + 1 :] in packages


def detect_import_path(module_path: str, version: str) -> str | None:
    """
    Work out the package to build for a Go module.

    Returns:
        None if the module root holds a package (no import_path needed), otherwise the
        import path of the module's only top-level package.

    Raises:
        AmbiguousImportPathError: if the root has no package and there are several
        top-level packages; the caller has to choose one.
        GoModuleResolutionError: if the module zip cannot be fetched or read, or the
        root has no package and there is no top-level package to use instead.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    packages = fetch_module_packages(module_path, version)
    if "" in packages:
        logger.info("Root package is importable, no import_path needed")
        return None

    candidates = import_path_candidates(module_path, packages)
    if not candidates:
        raise GoModuleResolutionError(
            f"{module_path}@{version} has no package at its root, and no top-level package "
            "to build instead"
        )
    if len(candidates) > 1:
        raise AmbiguousImportPathError(module_path, version, packages, candidates)

    logger.info(f"Root package not importable, using its only top-level package {candidates[0]}")
    return candidates[0]


def validate_import_path(module_path: str, version: str, import_path: str) -> None:
    """
    Check that import_path names a package inside the module at this version.

    Raises:
        GoModuleResolutionError: if it does not, or the module zip cannot be fetched or read.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    if import_path != module_path and not import_path.startswith(f"{module_path}/"):
        raise GoModuleResolutionError(
            f"Import path {import_path} is not inside module {module_path}"
        )

    packages = fetch_module_packages(module_path, version)
    if not is_package_in_module(module_path, import_path, packages):
        raise GoModuleResolutionError(
            f"Import path {import_path} is not a package in {module_path}@{version}: "
            "it has no non-test .go files there"
        )


def version_to_key(version: str) -> str:
    """
    Convert a Go module version to a properties version key.

    Examples:
        v1.6.0 -> v160
        v1.36.0 -> v1360
        v0.9.1 -> v091
    """
    return re.sub(r"[^a-z0-9]", "", version.lower())


class GoHandler:
    """Handles Go library additions to Compiler Explorer infrastructure."""

    def __init__(
        self,
        infra_path: Path,
        main_path: Path | None = None,
        setup_ce_install: bool = True,
        debug: bool = False,
    ):
        self.infra_path = infra_path
        self.main_path = main_path
        self.debug = debug
        if setup_ce_install:
            self.setup_ce_install()

    def setup_ce_install(self) -> bool:
        """Ensure ce_install is available"""
        return setup_ce_install_shared(self.infra_path, self.debug)

    @staticmethod
    def suggest_library_id_static(module_path: str) -> str:
        """Generate a suggested library ID from Go module path"""
        return suggest_library_id_from_module(module_path)

    def add_library(self, config: LibraryConfig) -> str | None:
        """
        Add Go library to libraries.yaml.
        Returns library_id if successful, None otherwise.
        """
        try:
            if not config.module:
                raise ValueError("Go module path is required")

            library_id = config.library_id or self.suggest_library_id_static(config.module)

            # Ensure version has 'v' prefix (Go convention)
            version = config.version
            if isinstance(version, str) and not version.startswith("v"):
                version = f"v{version}"

            # Read existing libraries.yaml
            libraries_yaml_path = self.infra_path / LIBRARIES_YAML_PATH
            if not libraries_yaml_path.exists():
                logger.error(f"libraries.yaml not found at {libraries_yaml_path}")
                return None

            yaml = round_trip_yaml()
            with open(libraries_yaml_path, encoding="utf-8") as f:
                data = yaml.load(f)

            if "libraries" not in data:
                data["libraries"] = {}

            libraries = data["libraries"]
            if "go" not in libraries:
                insert_sorted(libraries, "go", {})

            go_libs = libraries["go"]

            if library_id in go_libs:
                # Library exists - add version to targets
                existing = go_libs[library_id]
                targets = existing.get("targets", [])
                if version not in targets:
                    targets.append(version)
                    existing["targets"] = targets
                    logger.info(f"Added version {version} to existing Go library {library_id}")
                else:
                    logger.info(f"Version {version} already exists for Go library {library_id}")
            else:
                # Create new library entry
                library_entry = {
                    "build_type": "gomod",
                    "module": config.module,
                    "targets": [version],
                    "type": "gomod",
                }
                if config.import_path:
                    library_entry["import_path"] = config.import_path
                insert_sorted(go_libs, library_id, library_entry)
                logger.info(
                    f"Added new Go library {library_id} ({config.module}) with version {version}"
                )

            # Save updated libraries.yaml
            with open(libraries_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f)

            return library_id

        except Exception as e:
            logger.error(f"Error adding Go library: {e}")
            return None

    def update_go_properties(self, library_id: str, config: LibraryConfig) -> bool:
        """
        Update the main repo's go.amazon.properties file with the new library.
        Returns True if successful, False otherwise.
        """
        if not self.main_path:
            logger.error(MAIN_REPO_PATH_REQUIRED)
            return False

        try:
            props_file = self.main_path / GO_PROPERTIES_PATH

            if not props_file.exists():
                logger.error(f"Go properties file not found: {props_file}")
                return False

            with open(props_file, encoding="utf-8") as f:
                content = f.read()

            # Ensure version has 'v' prefix
            version = config.version
            if isinstance(version, str) and not version.startswith("v"):
                version = f"v{version}"

            version_key = version_to_key(version)
            lookupname = f"go_{library_id}"

            name = display_name_from_module(config.module) if config.module else library_id

            repo_url = module_repo_url(config.module) if config.module else None

            # Build library properties
            library_props = []
            library_props.append(f"libs.{library_id}.name={name}")
            if repo_url:
                library_props.append(f"libs.{library_id}.url={repo_url}")
            library_props.append(f"libs.{library_id}.lookupname={lookupname}")
            library_props.append(f"libs.{library_id}.packagedheaders=true")
            library_props.append(f"libs.{library_id}.versions={version_key}")
            version_line = f"libs.{library_id}.versions.{version_key}.version={version}"
            library_props.append(version_line)

            updated = add_version_to_existing_library(
                content, library_id, version_key, [version_line]
            )
            if updated is None:
                content = insert_library_properties(content, library_props)
            elif updated == content:
                logger.info(f"Version {version_key} already exists in properties")
            else:
                content = updated

            with open(props_file, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Successfully updated {props_file.name}")
            return True

        except Exception as e:
            logger.error(f"Error updating Go properties: {e}")
            return False

    def is_build_test_available(self) -> tuple[bool, str]:
        """
        Check if Go build testing is available (Go compiler installed).

        Returns:
            Tuple of (available, message)
        """
        return check_go_build_test_available(self.infra_path, self.debug)

    def run_build_test(
        self,
        library_id: str,
        version: str,
        compiler_id: str | None = None,
    ) -> BuildTestResult:
        """
        Test building the Go library using ce_install build command.

        Args:
            library_id: The library identifier
            version: The library version
            compiler_id: Specific Go compiler ID to use (auto-detected if None)

        Returns:
            BuildTestResult with success status, message, and artifact information
        """
        return run_go_build_test(
            infra_path=self.infra_path,
            library_id=library_id,
            version=version,
            compiler_id=compiler_id,
            debug=self.debug,
        )

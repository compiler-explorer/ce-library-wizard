"""Handle Go library additions to Compiler Explorer."""
from __future__ import annotations

import io
import logging
import re
import urllib.request
import zipfile
from pathlib import Path

import yaml

from .build_tester import (
    BuildTestResult,
    check_go_build_test_available,
    run_go_build_test,
)
from .constants import GO_PROPERTIES_PATH, LIBRARIES_YAML_PATH, MAIN_REPO_PATH_REQUIRED
from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .models import LibraryConfig

logger = logging.getLogger(__name__)

GO_PROXY_URL = "https://proxy.golang.org"


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


class GoModuleResolutionError(ValueError):
    """Raised when no module the Go proxy serves can be found for the given path."""


def escape_module_path(module_path: str) -> str:
    """Escape a module path for the Go proxy: each uppercase letter becomes '!' + lowercase."""
    return re.sub(r"[A-Z]", lambda m: "!" + m.group(0).lower(), module_path)


def normalise_module_input(module_path: str) -> str:
    """Strip whitespace, a URL scheme and trailing slashes from a user-entered module path."""
    return re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", module_path.strip()).rstrip("/")


def parse_go_mod_module(go_mod: str) -> str | None:
    """Return the path from a go.mod file's `module` line, or None if there isn't one."""
    for line in go_mod.splitlines():
        match = re.match(r"^\s*module\s+(\S+)", line)
        if match:
            return match.group(1).strip('"`')
    return None


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

    declared = parse_go_mod_module(go_mod)
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

    original = normalise_module_input(module_path)
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


def _pick_best_subpackage(module_path: str, subpackages: set[str]) -> str:
    """
    Pick the most likely "main" subpackage from candidates.

    Heuristics (in priority order):
    1. Subpackage whose name is a prefix of the module name or vice versa
       (e.g., "proto" for module "protobuf")
    2. Shortest name among remaining candidates
    3. Alphabetically first as tiebreaker
    """
    module_name = module_path.rstrip("/").split("/")[-1].lower()
    candidates = sorted(subpackages)

    # Look for prefix relationship with module name
    for sub in candidates:
        sub_lower = sub.lower()
        if module_name.startswith(sub_lower) or sub_lower.startswith(module_name):
            return sub

    # Fall back to shortest name (likely the most "core" package)
    return min(candidates, key=lambda s: (len(s), s))


def detect_import_path(module_path: str, version: str) -> str | None:
    """
    Detect if a Go module needs an import_path override by checking
    whether the root package has importable Go source files.

    Downloads the module zip from the Go proxy and inspects the file listing.

    Args:
        module_path: Go module path (e.g., google.golang.org/protobuf)
        version: Version string (e.g., v1.36.0)

    Returns:
        None if the root package is importable (no override needed),
        or the import path of the best subpackage to use as override.
    """
    if not version.startswith("v"):
        version = f"v{version}"

    zip_url = f"{GO_PROXY_URL}/{escape_module_path(module_path)}/@v/{version}.zip"
    logger.info(f"Checking module structure from {zip_url}")

    try:
        with urllib.request.urlopen(zip_url, timeout=30) as response:
            zip_data = io.BytesIO(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        logger.warning(f"Could not download module zip: {e}")
        return None

    try:
        with zipfile.ZipFile(zip_data) as zf:
            # The zip has paths like: module@version/file.go
            prefix = f"{module_path}@{version}/"
            root_has_go = False
            subpackages: set[str] = set()

            for name in zf.namelist():
                if not name.startswith(prefix):
                    continue

                rel = name[len(prefix) :]
                if not rel:
                    continue

                parts = rel.split("/")

                # Check for .go files in root (not test files, not build tag only)
                if len(parts) == 1 and parts[0].endswith(".go"):
                    fname = parts[0]
                    if fname.endswith("_test.go"):
                        continue
                    # Read file to check it has a real package declaration
                    # (some roots only have doc.go with no exported symbols,
                    # but that's still importable)
                    root_has_go = True

                # Track subpackages that have .go files
                if len(parts) >= 2 and parts[-1].endswith(".go"):
                    if parts[-1].endswith("_test.go"):
                        continue
                    subdir = parts[0]
                    # Skip non-library directories
                    skip_dirs = {
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
                    if subdir in skip_dirs:
                        continue
                    subpackages.add(subdir)

            if root_has_go:
                logger.info("Root package is importable, no override needed")
                return None

            if not subpackages:
                logger.warning("No importable subpackages found")
                return None

            best = _pick_best_subpackage(module_path, subpackages)
            import_path = f"{module_path}/{best}"
            logger.info(
                f"Root package not importable, suggesting: {import_path} "
                f"(from {len(subpackages)} candidates: {sorted(subpackages)[:5]})"
            )
            return import_path

    except zipfile.BadZipFile:
        logger.warning("Invalid zip file from module proxy")
        return None


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

            with open(libraries_yaml_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if "libraries" not in data:
                data["libraries"] = {}

            libraries = data["libraries"]
            if "go" not in libraries:
                libraries["go"] = {}

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
                go_libs[library_id] = library_entry
                logger.info(
                    f"Added new Go library {library_id} ({config.module}) with version {version}"
                )

            # Save updated libraries.yaml
            with open(libraries_yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

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

            # Derive GitHub URL from module path
            github_url = module_to_github_url(config.module) if config.module else None

            # Build library properties
            library_props = []
            library_props.append(f"libs.{library_id}.name={name}")
            if github_url:
                library_props.append(f"libs.{library_id}.url={github_url}")
            library_props.append(f"libs.{library_id}.lookupname={lookupname}")
            library_props.append(f"libs.{library_id}.packagedheaders=true")
            library_props.append(f"libs.{library_id}.versions={version_key}")
            library_props.append(f"libs.{library_id}.versions.{version_key}.version={version}")

            # Check if this library already has properties
            lib_pattern = re.compile(rf"^libs\.{re.escape(library_id)}\.", re.MULTILINE)
            existing_match = lib_pattern.search(content)

            if existing_match:
                # Library exists - check if we need to add a new version
                versions_pattern = re.compile(
                    rf"^libs\.{re.escape(library_id)}\.versions=(.*)$", re.MULTILINE
                )
                versions_match = versions_pattern.search(content)
                if versions_match:
                    current_versions = versions_match.group(1)
                    if version_key not in current_versions:
                        # Add new version key to versions list
                        new_versions = f"{current_versions}:{version_key}"
                        content = content.replace(
                            versions_match.group(0),
                            f"libs.{library_id}.versions={new_versions}",
                        )

                        # Add new version entry before the next library or at end of libs section
                        version_entry = (
                            f"libs.{library_id}.versions.{version_key}.version={version}"
                        )

                        # Find the last property line for this library
                        last_lib_line = None
                        for match in re.finditer(
                            rf"^libs\.{re.escape(library_id)}\..*$", content, re.MULTILINE
                        ):
                            last_lib_line = match

                        if last_lib_line:
                            insert_pos = last_lib_line.end()
                            content = (
                                content[:insert_pos] + "\n" + version_entry + content[insert_pos:]
                            )
                    else:
                        logger.info(f"Version {version_key} already exists in properties")
            else:
                # New library - add properties
                # Find insertion point - append at end of file
                # Look for tools section delimiter
                tools_section_match = re.search(
                    r"\n(#{33}\n#{33}\n# Installed tools)",
                    content,
                )

                if tools_section_match:
                    insertion_point = tools_section_match.start()
                    content = (
                        content[:insertion_point]
                        + "\n"
                        + "\n".join(library_props)
                        + "\n\n"
                        + content[insertion_point:]
                    )
                else:
                    # Just append at end
                    if not content.endswith("\n"):
                        content += "\n"
                    content += "\n" + "\n".join(library_props) + "\n"

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

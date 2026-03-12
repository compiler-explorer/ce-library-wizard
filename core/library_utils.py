"""Shared utilities for library handlers."""
import logging
import re
import tempfile
from pathlib import Path

from .models import LibraryType
from .subprocess_utils import run_ce_install_command, run_command, run_make_command

logger = logging.getLogger(__name__)


def clone_repository(github_url: str, clone_path: Path) -> bool:
    """
    Clone a GitHub repository to the specified path.

    Args:
        github_url: GitHub repository URL
        clone_path: Path where to clone the repository

    Returns:
        True if cloning succeeded, False otherwise
    """
    try:
        result = run_command(
            ["git", "clone", "--depth", "1", github_url, str(clone_path)], clean_env=False
        )

        if result.returncode != 0:
            logger.error(f"Failed to clone repository: {result.stderr}")
            return False

        return True

    except Exception as e:
        logger.error(f"Error cloning repository: {e}")
        return False


def analyze_repository_structure(clone_path: Path) -> dict:
    """
    Analyze a cloned repository structure to determine build system and targets.

    Args:
        clone_path: Path to the cloned repository

    Returns:
        Dict with analysis results:
        {
            'has_cmake': bool,
            'cmake_targets': list[str] | None,
            'main_targets': list[str] | None,
            'library_artifacts': list[str],  # e.g. ["libminiz.a"]
            'has_generated_headers': bool,
            'check_file': str | None  # e.g. "include/named/named.hpp"
        }
    """
    analysis = {
        "has_cmake": False,
        "cmake_targets": None,
        "main_targets": None,
        "library_artifacts": [],
        "has_generated_headers": False,
        "check_file": None,
    }

    try:
        # Check for CMakeLists.txt existence
        cmake_file = clone_path / "CMakeLists.txt"
        analysis["has_cmake"] = cmake_file.exists()

        # Try to get CMake targets if CMakeLists.txt exists
        if analysis["has_cmake"]:
            build_path = clone_path / "build"
            analysis["cmake_targets"] = get_cmake_targets_from_path(clone_path, build_path)
            if analysis["cmake_targets"]:
                analysis["main_targets"] = filter_main_cmake_targets(analysis["cmake_targets"])
                analysis["library_artifacts"] = get_library_artifacts_from_build(build_path)
                analysis["has_generated_headers"] = has_generated_headers(clone_path, build_path)
                logger.info(f"Found {len(analysis['cmake_targets'])} CMake targets")
                if analysis["main_targets"]:
                    logger.info(f"Filtered to {len(analysis['main_targets'])} main targets")
                if analysis["library_artifacts"]:
                    logger.info(f"Found library artifacts: {analysis['library_artifacts']}")
                if analysis["has_generated_headers"]:
                    logger.info("Detected generated headers in build directory")

        # Detect a suitable check_file for verifying successful clone
        analysis["check_file"] = detect_check_file(clone_path)
        if analysis["check_file"]:
            logger.info(f"Detected check_file: {analysis['check_file']}")

        return analysis

    except Exception as e:
        logger.error(f"Error analyzing repository structure: {e}")
        return analysis


def detect_check_file(clone_path: Path) -> str | None:
    """
    Detect a suitable check_file from a cloned repository.

    Looks for a header file under include/ first, then falls back to
    any README variant in the repo root.

    Args:
        clone_path: Path to the cloned repository

    Returns:
        Relative path to a suitable check_file, or None
    """
    header_exts = (".h", ".hpp", ".hxx", ".hh")

    # Look for header files under include/
    include_dir = clone_path / "include"
    if include_dir.is_dir():
        for header in sorted(include_dir.rglob("*")):
            if header.is_file() and header.suffix in header_exts:
                return str(header.relative_to(clone_path))

    # Fall back to any README variant in the repo root
    for entry in sorted(clone_path.iterdir()):
        if entry.is_file() and entry.stem.lower() == "readme":
            return entry.name

    return None


def clone_and_analyze_repository(github_url: str) -> tuple[bool, dict]:
    """
    Clone a repository and analyze its structure in a temporary directory.

    Args:
        github_url: GitHub repository URL

    Returns:
        Tuple of (success, analysis_results)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / "repo"

        # Clone the repository
        if not clone_repository(github_url, clone_path):
            return False, {}

        # Analyze the repository structure
        analysis = analyze_repository_structure(clone_path)
        return True, analysis


def get_cmake_targets_from_path(clone_path: Path, build_path: Path) -> list[str] | None:
    """
    Get CMake targets from an already cloned repository path.

    Args:
        clone_path: Path to the cloned repository
        build_path: Path to use for the cmake build directory

    Returns:
        List of library target names, or None on error
    """
    try:
        # Configure CMake with Debug build type to match ce_install
        result = run_command(
            [
                "cmake",
                "-B",
                str(build_path),
                "-S",
                str(clone_path),
                "-DCMAKE_BUILD_TYPE=Debug",
            ],
            clean_env=False,
        )

        if result.returncode != 0:
            logger.debug(f"Failed to configure CMake: {result.stderr}")
            return None

        # Get list of targets
        result = run_command(
            ["cmake", "--build", str(build_path), "--target", "help"], clean_env=False
        )

        if result.returncode != 0:
            logger.debug(f"Failed to get CMake targets: {result.stderr}")
            return None

        # Parse targets from output
        targets = []
        for line in result.stdout.splitlines():
            if line.startswith("... ") and not any(
                skip in line
                for skip in [
                    "all",
                    "clean",
                    "depend",
                    "edit_cache",
                    "install",
                    "rebuild_cache",
                    "test",
                    "Continuous",
                    "Experimental",
                    "Nightly",
                    "help",
                ]
            ):
                target = line[4:].strip()
                targets.append(target)

        return targets

    except Exception as e:
        logger.debug(f"Error getting CMake targets: {e}")
        return None


def get_library_artifacts_from_build(build_path: Path) -> list[str]:
    """
    Parse cmake link.txt files to find library artifacts (.a/.so) that will be produced.

    After cmake configure, each linkable target has a link.txt in
    build/CMakeFiles/<target>.dir/link.txt containing the link command.

    Returns list of artifact filenames (e.g., ["libminiz.a", "libfoo.so"]).
    """
    simple = []
    versioned = []
    link_files = list(build_path.glob("CMakeFiles/*.dir/link.txt"))
    logger.debug(f"Found {len(link_files)} link.txt files in {build_path}")

    for link_file in link_files:
        try:
            content = link_file.read_text(encoding="utf-8", errors="replace")
            tokens = content.split()
            for token in tokens:
                filename = Path(token).name
                if filename.startswith("lib") and (filename.endswith(".a") or ".so" in filename):
                    target = simple if filename.count(".") == 1 else versioned
                    if filename not in target:
                        target.append(filename)
        except Exception as e:
            logger.debug(f"Error reading {link_file}: {e}")

    artifacts = simple if simple else versioned
    logger.debug(f"Found library artifacts: {artifacts}")
    return artifacts


def has_generated_headers(clone_path: Path, build_path: Path) -> bool:
    """
    Check if cmake generated any header files in the build directory.

    Generated headers (e.g. from generate_export_header()) only exist in
    the build tree. If present, the library needs packaged-headers type
    so cmake --install places them in the include directory.
    """
    header_exts = (".h", ".hpp", ".hxx", ".hh")
    for header in build_path.rglob("*"):
        if header.is_file() and header.suffix in header_exts:
            # Ignore CMake's own internal headers
            if "CMakeFiles" in header.parts:
                continue
            logger.debug(f"Found generated header: {header}")
            return True
    return False


def filter_main_cmake_targets(targets: list[str]) -> list[str]:
    """
    Filter CMake targets to include only main library targets.

    Args:
        targets: List of all CMake targets

    Returns:
        List of filtered main targets
    """
    return [
        t
        for t in targets
        if not any(
            skip in t.lower()
            for skip in [
                "internal",
                "test",
                "example",
                "benchmark",
                "mock",
                "_test",
                "_tests",
                "_testing",
                "_bench",
                "_demo",
                "sample",
                "tutorial",
                "doc",
                "docs",
            ]
        )
    ]


def setup_ce_install(infra_path: Path, debug: bool = False) -> bool:
    """
    Ensure ce_install is available by running make ce.

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug mode

    Returns:
        True if successful

    Raises:
        RuntimeError: If setup fails
    """
    try:
        logger.info("Setting up ce_install...")

        result = run_make_command("ce", cwd=infra_path, debug=debug)

        if result.returncode != 0:
            logger.warning(f"Setup command failed with return code: {result.returncode}")

        return True

    except Exception as e:
        raise RuntimeError(f"Error setting up ce_install: {e}") from e


def suggest_library_id_from_github_url(github_url: str) -> str:
    """
    Suggest a library ID based on the GitHub URL.

    Args:
        github_url: GitHub repository URL

    Returns:
        Suggested library ID following naming conventions
    """
    # Extract repo name from URL
    match = re.search(r"github\.com/[^/]+/([^/]+)", str(github_url))
    if not match:
        return "unknown_library"

    repo_name = match.group(1)

    # Remove .git suffix if present
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    # Convert to lowercase and replace non-alphanumeric with underscores
    library_id = re.sub(r"[^a-z0-9]+", "_", repo_name.lower())

    # Remove consecutive underscores and leading/trailing underscores
    library_id = re.sub(r"_+", "_", library_id).strip("_")

    # Ensure it starts with a letter
    if library_id and not library_id[0].isalpha():
        library_id = "lib_" + library_id

    return library_id or "unknown_library"


def validate_cmake_targets_for_type(analysis: dict, library_type: LibraryType) -> tuple[bool, str]:
    """
    Validate cmake targets against the library type.

    Returns (is_ok, message):
    - is_ok=True: validation passed (message may be informational)
    - is_ok=False: validation failed (message describes the error)
    """
    artifacts = analysis.get("library_artifacts", [])
    has_library_artifacts = len(artifacts) > 0

    if library_type in (LibraryType.STATIC, LibraryType.SHARED, LibraryType.CSHARED):
        if not has_library_artifacts:
            return (
                False,
                "CMake targets do not indicate library artifacts (.a/.so) will be produced",
            )
        if analysis.get("has_generated_headers"):
            return (
                True,
                "CMake generates headers during build"
                " — using package_install for cmake --install",
            )
        return (True, "")

    if library_type == LibraryType.PACKAGED_HEADERS:
        if has_library_artifacts and not analysis.get("has_generated_headers"):
            return (
                False,
                "CMake targets indicate library artifacts (.a/.so) will be produced"
                " — this may not be a packaged-headers library",
            )
        return (True, "")

    # header-only: no validation needed
    return (True, "")


def detect_library_type_from_analysis(
    analysis: dict, existing_config: dict | None = None
) -> tuple[bool, str | None]:
    """
    Determine library type based on repository analysis and existing configuration.

    Args:
        analysis: Repository analysis results from analyze_repository_structure
        existing_config: Existing library configuration if available

    Returns:
        Tuple of (is_valid, library_type_value)
    """
    # First check existing configuration if available
    if existing_config:
        # Check if it's explicitly marked as header-only via build_type
        build_type = existing_config.get("build_type")
        if build_type == "none":
            logger.info("Using existing configuration: library is header-only (build_type: none)")
            return True, LibraryType.HEADER_ONLY.value

        # Check lib_type field (used by tarballs/make-based libraries like ICU)
        explicit_lib_type = existing_config.get("lib_type")
        if explicit_lib_type in ("header-only", "packaged-headers", "static", "shared", "cshared"):
            logger.info(f"Using existing configuration: library is {explicit_lib_type} (lib_type)")
            return True, explicit_lib_type

        # Check type field (used by github-based libraries)
        lib_type = existing_config.get("type")
        if lib_type == "header-only":
            logger.info("Using existing configuration: library is header-only")
            return True, LibraryType.HEADER_ONLY.value
        elif lib_type == "packaged-headers":
            logger.info("Using existing configuration: library is packaged-headers")
            return True, LibraryType.PACKAGED_HEADERS.value
        elif lib_type == "static":
            logger.info("Using existing configuration: library is static")
            return True, LibraryType.STATIC.value
        elif lib_type == "shared":
            logger.info("Using existing configuration: library is shared")
            return True, LibraryType.SHARED.value
        elif lib_type == "cshared":
            logger.info("Using existing configuration: library is cshared")
            return True, LibraryType.CSHARED.value

        # If it's type: github with no explicit build_type, it might be header-only by default
        if lib_type == "github" and build_type is None:
            logger.info(
                "Using existing configuration: library is likely header-only "
                "(type: github, no build_type)"
            )
            return True, LibraryType.HEADER_ONLY.value

        # If existing config doesn't have clear type info, continue with detection
        logger.warning("Could not determine type from existing config, falling back to detection")

    # Detect based on repository analysis
    if analysis.get("has_cmake"):
        artifacts = analysis.get("library_artifacts", [])
        if any(a.endswith(".a") for a in artifacts):
            return True, LibraryType.STATIC.value
        elif any(a.endswith(".so") or ".so." in a for a in artifacts):
            return True, LibraryType.SHARED.value
        else:
            return True, LibraryType.PACKAGED_HEADERS.value
    else:
        # No CMakeLists.txt, could be header-only or require manual configuration
        return True, LibraryType.HEADER_ONLY.value


def get_link_targets_from_analysis(
    analysis: dict, library_type_value: str
) -> dict[str, list[str]] | None:
    """
    Get link targets from repository analysis, separated by artifact type.

    When library_artifacts are available (parsed from cmake link.txt files),
    derive link names from them (strip lib prefix and .a/.so suffix),
    categorized into 'static' (.a) and 'shared' (.so) buckets.
    Otherwise fall back to cmake main_targets under the requested type.

    Args:
        analysis: Repository analysis results
        library_type_value: Library type value (e.g., 'static', 'shared', 'cshared')

    Returns:
        Dict with 'static' and/or 'shared' keys mapping to link name lists,
        or None if not applicable
    """
    if library_type_value not in ["static", "shared", "cshared"]:
        return None

    artifacts = analysis.get("library_artifacts", [])
    if artifacts:
        static_names = []
        shared_names = []
        for artifact in artifacts:
            name = artifact
            if name.startswith("lib"):
                name = name[3:]
            if name.endswith(".a"):
                link_name = name[:-2]
                if link_name and link_name not in static_names:
                    static_names.append(link_name)
            elif ".so" in name:
                link_name = name[: name.index(".so")]
                if link_name and link_name not in shared_names:
                    shared_names.append(link_name)

        result = {}
        if static_names:
            result["static"] = static_names
        if shared_names:
            result["shared"] = shared_names
        return result if result else None

    if analysis.get("main_targets"):
        if library_type_value == "static":
            return {"static": analysis["main_targets"]}
        else:
            return {"shared": analysis["main_targets"]}
    return None


def check_ce_install_link_support(infra_path: Path) -> dict[str, bool]:
    """
    Check which link target parameters are supported by ce_install.

    Args:
        infra_path: Path to the infra repository

    Returns:
        Dict with support status for different link parameters
    """
    try:
        help_result = run_ce_install_command(
            ["cpp-library", "add", "--help"], cwd=infra_path, debug=False
        )

        return {
            "static_lib_link": "--static-lib-link" in help_result.stdout,
            "shared_lib_link": "--shared-lib-link" in help_result.stdout,
        }
    except Exception as e:
        logger.warning(f"Could not check ce_install link support: {e}")
        return {"static_lib_link": False, "shared_lib_link": False}


def build_ce_install_command(
    config,
    library_type_value: str | None,
    link_targets: dict[str, list[str]] | None,
    link_support: dict[str, bool],
    check_file: str | None = None,
) -> list[str]:
    """
    Build the ce_install command with appropriate parameters.

    Args:
        config: Library configuration object
        library_type_value: Library type value (can be None)
        link_targets: Dict with 'static' and/or 'shared' keys mapping to link names
        link_support: Dict indicating which link parameters are supported
        check_file: File path to verify successful clone (e.g. "include/foo.h")

    Returns:
        List of command arguments
    """
    subcommand = ["cpp-library", "add", str(config.github_url), config.version]

    if library_type_value:
        subcommand.extend(["--type", library_type_value])
        logger.info(f"Adding library with type: {library_type_value}")
    else:
        logger.warning("No library type specified, using default behavior")

    # Add target prefix if specified
    if hasattr(config, "target_prefix") and config.target_prefix:
        subcommand.extend(["--target-prefix", config.target_prefix])
        logger.info(f"Adding target prefix: {config.target_prefix}")

    # Add package install flag if specified
    if hasattr(config, "package_install") and config.package_install:
        subcommand.append("--package-install")
        logger.info("Adding --package-install flag for CMake header configuration")

    # Add check_file if specified
    if check_file:
        subcommand.extend(["--check-file", check_file])
        logger.info(f"Adding check file: {check_file}")

    # Add link targets if supported and available
    # ce_install restricts which flags can be used with each type:
    #   --static-lib-link: only with --type static
    #   --shared-lib-link: only with --type shared or cshared
    if link_targets:
        static_links = link_targets.get("static", [])
        shared_links = link_targets.get("shared", [])

        if static_links and library_type_value == "static":
            if link_support.get("static_lib_link"):
                subcommand.extend(["--static-lib-link", ",".join(static_links)])
                logger.info(f"Adding static library link targets: {', '.join(static_links)}")
        if shared_links and library_type_value in ("shared", "cshared"):
            if link_support.get("shared_lib_link"):
                subcommand.extend(["--shared-lib-link", ",".join(shared_links)])
                logger.info(f"Adding shared library link targets: {', '.join(shared_links)}")

    return subcommand


def supplement_properties_from_yaml(
    props_file: Path,
    library_id: str,
    github_url: str | None,
    infra_path: Path,
) -> bool:
    """
    Supplement a properties file with fields from libraries.yaml that
    ce_install generate-linux-props doesn't produce (e.g. for tarballs/make-based libs).

    Args:
        props_file: Path to the properties file to supplement
        library_id: The library identifier
        github_url: GitHub URL of the library
        infra_path: Path to the infra repository

    Returns:
        True if properties were supplemented, False otherwise
    """
    from .models import check_existing_library_config

    if not props_file.exists():
        return False

    yaml_config = check_existing_library_config(github_url or "", library_id, infra_path)
    if not yaml_config:
        return False

    content = props_file.read_text(encoding="utf-8")
    prefix = f"libs.{library_id}."

    # Only supplement if the library entry exists in the properties
    if prefix not in content:
        return False

    additions = []

    # Supplement url if missing
    if f"{prefix}url=" not in content and github_url:
        additions.append(f"{prefix}url={github_url}")

    # Supplement sharedliblink if missing
    if f"{prefix}sharedliblink=" not in content:
        shared_libs = yaml_config.get("sharedliblink")
        if shared_libs and isinstance(shared_libs, list):
            additions.append(f"{prefix}sharedliblink={':'.join(shared_libs)}")

    # Supplement staticliblink if missing
    if f"{prefix}staticliblink=" not in content:
        static_libs = yaml_config.get("staticliblink")
        if static_libs and isinstance(static_libs, list):
            additions.append(f"{prefix}staticliblink={':'.join(static_libs)}")

    # Supplement packagedheaders if missing
    if f"{prefix}packagedheaders=" not in content:
        if yaml_config.get("package_install"):
            additions.append(f"{prefix}packagedheaders=true")

    if not additions:
        return False

    # Insert additions after the last existing property line for this library
    lines = content.split("\n")
    last_lib_line_idx = -1
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            last_lib_line_idx = i

    if last_lib_line_idx >= 0:
        for addition in reversed(additions):
            lines.insert(last_lib_line_idx + 1, addition)
        props_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Supplemented {len(additions)} properties for {library_id}")
        return True

    return False

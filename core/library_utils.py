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
            'main_targets': list[str] | None
        }
    """
    analysis = {"has_cmake": False, "cmake_targets": None, "main_targets": None}

    try:
        # Check for CMakeLists.txt existence
        cmake_file = clone_path / "CMakeLists.txt"
        analysis["has_cmake"] = cmake_file.exists()

        # Try to get CMake targets if CMakeLists.txt exists
        if analysis["has_cmake"]:
            analysis["cmake_targets"] = get_cmake_targets_from_path(clone_path)
            if analysis["cmake_targets"]:
                analysis["main_targets"] = filter_main_cmake_targets(analysis["cmake_targets"])
                logger.info(f"Found {len(analysis['cmake_targets'])} CMake targets")
                if analysis["main_targets"]:
                    logger.info(f"Filtered to {len(analysis['main_targets'])} main targets")

        return analysis

    except Exception as e:
        logger.error(f"Error analyzing repository structure: {e}")
        return analysis


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


def get_cmake_targets_from_path(clone_path: Path) -> list[str] | None:
    """
    Get CMake targets from an already cloned repository path.

    Args:
        clone_path: Path to the cloned repository

    Returns:
        List of library target names, or None on error
    """
    try:
        # Configure CMake
        build_path = clone_path / "build"
        result = run_command(
            ["cmake", "-B", str(build_path), "-S", str(clone_path)], clean_env=False
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

        # Check legacy type field
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
        # Has CMakeLists.txt, assume it's a packaged-headers library
        return True, LibraryType.PACKAGED_HEADERS.value
    else:
        # No CMakeLists.txt, could be header-only or require manual configuration
        return True, LibraryType.HEADER_ONLY.value


def get_link_targets_from_analysis(analysis: dict, library_type_value: str) -> list[str] | None:
    """
    Get link targets from repository analysis based on library type.

    Args:
        analysis: Repository analysis results
        library_type_value: Library type value (e.g., 'static', 'shared', 'cshared')

    Returns:
        List of link targets or None if not applicable
    """
    if library_type_value in ["static", "shared", "cshared"] and analysis.get("main_targets"):
        return analysis["main_targets"]
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


def update_properties_libs_line(content: str, library_id: str) -> str:
    """
    Update the libs= line in a properties file to include a new library.

    Args:
        content: The properties file content
        library_id: The library ID to add

    Returns:
        Updated content with the library added to libs= line
    """
    libs_match = re.search(r"^libs=(.*)$", content, re.MULTILINE)
    if libs_match:
        current_libs = libs_match.group(1)
        # Add new library to the list if not already there
        if library_id not in current_libs:
            new_libs_line = f"libs={current_libs}:{library_id}"
            content = content.replace(libs_match.group(0), new_libs_line)

    return content


def build_ce_install_command(
    config,
    library_type_value: str | None,
    link_targets: list[str] | None,
    link_support: dict[str, bool],
) -> list[str]:
    """
    Build the ce_install command with appropriate parameters.

    Args:
        config: Library configuration object
        library_type_value: Library type value (can be None)
        link_targets: List of link targets if available
        link_support: Dict indicating which link parameters are supported

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

    # Add link targets if supported and available
    if link_targets:
        link_targets_str = ",".join(link_targets)

        if library_type_value == "static" and link_support.get("static_lib_link"):
            subcommand.extend(["--static-lib-link", link_targets_str])
            logger.info("Adding static library link targets to command")
        elif library_type_value in ["shared", "cshared"] and link_support.get("shared_lib_link"):
            subcommand.extend(["--shared-lib-link", link_targets_str])
            logger.info("Adding shared library link targets to command")
        elif link_targets:
            logger.info(
                f"Note: CMake targets detected but ce_install doesn't support "
                f"automatic link target configuration yet. You may need to manually "
                f"configure link targets: {', '.join(link_targets[:3])}"
                + (f" and {len(link_targets)-3} more" if len(link_targets) > 3 else "")
            )

    return subcommand

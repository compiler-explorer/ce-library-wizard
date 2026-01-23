"""Handle C library additions to Compiler Explorer."""
from __future__ import annotations

import logging
from pathlib import Path

from .build_tester import BuildTestResult, check_build_test_available, run_build_test
from .library_utils import (
    build_ce_install_command,
    check_ce_install_link_support,
    clone_and_analyze_repository,
    detect_library_type_from_analysis,
    get_link_targets_from_analysis,
    suggest_library_id_from_github_url,
)
from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .models import LibraryConfig, LibraryType, check_existing_library_config
from .subprocess_utils import run_ce_install_command

logger = logging.getLogger(__name__)


class CHandler:
    """Handles C library additions to Compiler Explorer infrastructure."""

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

    def detect_library_type(
        self, github_url: str, library_id: str | None = None
    ) -> tuple[bool, LibraryType | None]:
        """
        Clone repository and detect if it's header-only by checking for CMakeLists.txt.
        Also checks existing library configuration if available.

        Returns:
            Tuple of (is_valid, library_type)
        """
        # First check if library already exists and use its configuration
        existing_config = None
        if (
            library_id
            and hasattr(self, "infra_path")
            and self.infra_path
            and self.infra_path.exists()
        ):
            existing_config = check_existing_library_config(github_url, library_id, self.infra_path)

        # Clone and analyze the repository
        success, analysis = clone_and_analyze_repository(github_url)
        if not success:
            return False, None

        # Determine library type from analysis and existing config
        is_valid, library_type_value = detect_library_type_from_analysis(analysis, existing_config)
        if not is_valid:
            return False, None

        # For C libraries, prefer shared/cshared over other types when CMake is detected
        if library_type_value == "packaged-headers" and analysis.get("has_cmake"):
            library_type_value = "shared"

        # Convert string value back to LibraryType enum
        library_type = LibraryType(library_type_value)

        return True, library_type

    def add_library(self, config: LibraryConfig) -> str | None:
        """
        Add a C shared library using cpp-library add with --type cshared.
        C libraries are added to the C++ section in libraries.yaml with cshared type.

        Args:
            config: Library configuration

        Returns:
            Library ID if successful, None otherwise
        """
        try:
            # Build command for C library (using cshared type)
            logger.info("Detecting CMake targets for C shared library link configuration...")
            success, analysis = clone_and_analyze_repository(str(config.github_url))

            link_targets = None
            if success:
                link_targets = get_link_targets_from_analysis(analysis, "cshared")

                if link_targets:
                    logger.info(
                        f"Detected {len(link_targets)} CMake targets: {', '.join(link_targets[:5])}"
                        + (f" and {len(link_targets)-5} more" if len(link_targets) > 5 else "")
                    )
                else:
                    logger.warning("No suitable CMake targets found for linking")
            else:
                logger.warning("Could not analyze repository for CMake targets")

            # Check ce_install link support and build command
            link_support = check_ce_install_link_support(self.infra_path)
            subcommand = build_ce_install_command(config, "cshared", link_targets, link_support)

            result = run_ce_install_command(subcommand, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                error_output = f"{result.stdout} {result.stderr}".strip()
                logger.error(f"cpp-library add failed: {error_output}")
                return None

            # Parse the output to get the library ID
            output = result.stdout.strip()

            import re

            patterns = [
                r"Added version .+ to library (\\S+)",
                r"Library '([^']+)' is now available",
                r"--library (\\S+)",
                r"Found existing library '([^']+)'",
            ]

            library_id = None
            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    library_id = match.group(1)
                    break

            if library_id:
                logger.info(f"Successfully added C shared library with ID: {library_id}")
                return library_id
            else:
                logger.warning("Could not parse library ID from output, using suggested ID")
                return config.library_id

        except Exception as e:
            logger.error(f"Error adding C library: {e}")
            return None

    def generate_properties(self, library_id: str, version: str) -> bool:
        """
        Generate properties for both C++ and C properties files.
        C shared libraries with lib_type: cshared should be available to both C and C++ compilers.

        Args:
            library_id: The library identifier
            version: The library version

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.main_path:
                logger.error("Main repository path not provided")
                return False

            # Generate C++ properties first
            cpp_props_file = self.main_path / "etc" / "config" / "c++.amazon.properties"
            subcommand_cpp = [
                "cpp-library",
                "generate-linux-props",
                "--input-file",
                str(cpp_props_file),
                "--output-file",
                str(cpp_props_file),
                "--library",
                library_id,
                "--version",
                version,
            ]

            result = run_ce_install_command(subcommand_cpp, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                logger.error(f"generate-linux-props for C++ failed: {result.stderr}")
                return False

            logger.info("Successfully generated Linux C++ properties")

            # Generate C properties
            c_props_file = self.main_path / "etc" / "config" / "c.amazon.properties"
            subcommand_c = [
                "cpp-library",
                "generate-linux-props",
                "--input-file",
                str(c_props_file),
                "--output-file",
                str(c_props_file),
                "--library",
                library_id,
                "--version",
                version,
            ]

            result = run_ce_install_command(subcommand_c, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                logger.error(f"generate-linux-props for C failed: {result.stderr}")
                return False

            logger.info("Successfully generated Linux C properties")

            # Also generate Windows properties
            subcommand_windows = ["cpp-library", "generate-windows-props"]

            result = run_ce_install_command(
                subcommand_windows, cwd=self.infra_path, debug=self.debug
            )

            if result.returncode != 0:
                logger.error(f"generate-windows-props failed: {result.stderr}")
                # Don't fail if Windows props generation fails
                logger.warning("Windows properties generation failed, but continuing...")

            return True

        except Exception as e:
            logger.error(f"Error generating C properties: {e}")
            return False

    def validate_library_id(self, library_id: str) -> bool:
        """Instance method that calls the static method"""
        return self.validate_library_id_static(library_id)

    @staticmethod
    def validate_library_id_static(library_id: str) -> bool:
        """
        Validate that library ID follows lowercase_with_underscores convention.

        Args:
            library_id: The library identifier to validate

        Returns:
            True if valid, False otherwise
        """
        import re

        # Must be lowercase letters, numbers, and underscores only
        # Must start with a letter
        pattern = r"^[a-z][a-z0-9_]*$"
        return bool(re.match(pattern, library_id))

    def suggest_library_id(self, github_url: str) -> str:
        """Instance method that calls the static method"""
        return self.suggest_library_id_static(github_url)

    @staticmethod
    def suggest_library_id_static(github_url: str) -> str:
        """
        Suggest a library ID based on the GitHub URL.

        Args:
            github_url: GitHub repository URL

        Returns:
            Suggested library ID following naming conventions
        """
        return suggest_library_id_from_github_url(github_url)

    def check_library_paths(self, library_id: str, version: str) -> bool:
        """
        Check library paths using ce_install list-paths without installing.

        Args:
            library_id: The library identifier
            version: The library version

        Returns:
            True if paths are consistent with properties, False otherwise
        """
        import re

        try:
            logger.info(f"Checking paths for {library_id} {version}...")
            install_spec = f"{library_id} {version}"

            result = run_ce_install_command(
                ["list-paths", install_spec], cwd=self.infra_path, debug=self.debug
            )

            if result.returncode != 0:
                logger.error(f"Path check failed: {result.stderr}")
                return False

            # Parse the output from list-paths
            output = result.stdout + result.stderr

            if self.debug:
                logger.debug(f"list-paths output: {output}")

            # Look for the destination path in the output
            destination_path = None

            # Try to parse the list-paths output format
            list_paths_pattern = r"libraries/c/\\S+\\s+\\S+:\\s+(.+)"
            list_match = re.search(list_paths_pattern, output)

            if list_match:
                relative_path = list_match.group(1).strip()
                destination_path = f"/opt/compiler-explorer/{relative_path}"
                logger.info(f"Library destination path: {destination_path}")
            else:
                logger.warning("Could not parse destination path from list-paths output")
                logger.warning("Skipping path consistency check")
                return True

            # Check if destination path is in both properties files
            if self.main_path:
                props_files = [
                    self.main_path / "etc" / "config" / "c++.amazon.properties",
                    self.main_path / "etc" / "config" / "c.amazon.properties",
                ]

                for props_file in props_files:
                    if props_file.exists():
                        props_content = props_file.read_text()
                        if destination_path not in props_content:
                            logger.error(
                                f"Inconsistency detected: Destination path "
                                f"'{destination_path}' not found in {props_file.name}"
                            )
                            logger.error(
                                "This suggests the properties file and library "
                                "configuration are out of sync"
                            )
                            return False
                    else:
                        logger.warning(
                            f"Properties file {props_file.name} not found for verification"
                        )

            logger.info("Path check succeeded")
            return True

        except Exception as e:
            logger.error(f"Error during path check: {e}")
            return False

    def is_build_test_available(self) -> tuple[bool, str]:
        """
        Check if build testing is available (compiler installed).

        Returns:
            Tuple of (available, message)
        """
        return check_build_test_available(self.infra_path, self.debug)

    def run_build_test(
        self,
        library_id: str,
        version: str,
        compiler_id: str | None = None,
        compiler_family: str = "gcc",
    ) -> BuildTestResult:
        """
        Test building the library using ce_install build command.

        This requires a compiler to be installed via ce_install.

        Args:
            library_id: The library identifier
            version: The library version
            compiler_id: Specific compiler ID to use (auto-detected if None)
            compiler_family: Compiler family to use if auto-detecting

        Returns:
            BuildTestResult with success status, message, and artifact information
        """
        result = run_build_test(
            infra_path=self.infra_path,
            library_id=library_id,
            version=version,
            language="c",
            compiler_id=compiler_id,
            compiler_family=compiler_family,
            debug=self.debug,
        )

        if result.success:
            logger.info(result.message)
        else:
            logger.error(result.message)

        return result

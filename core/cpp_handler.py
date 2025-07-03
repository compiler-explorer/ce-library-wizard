"""Handle C++ library additions to Compiler Explorer."""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .library_utils import (
    suggest_library_id_from_github_url,
)
from .models import (
    LibraryConfig,
    LibraryType,
    check_existing_library_config,
    check_existing_library_config_remote,
)
from .subprocess_utils import run_ce_install_command, run_command

logger = logging.getLogger(__name__)


class CppHandler:
    """Handles C++ library additions to Compiler Explorer infrastructure."""

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
            and (self.infra_path / "bin" / "yaml" / "libraries.yaml").exists()
        ):
            # We have the infra repo locally with libraries.yaml
            existing_config = check_existing_library_config(github_url, library_id, self.infra_path)
        elif library_id:
            # We don't have the repo yet (interactive mode), check remotely
            logger.info(f"Checking for existing configuration of {library_id}...")
            existing_config = check_existing_library_config_remote(github_url, library_id)

        if existing_config:
            # Library exists, try to determine type from existing config

            # Check if it's explicitly marked as header-only via build_type
            build_type = existing_config.get("build_type")
            if build_type == "none":
                logger.info(
                    f"Using existing configuration: {library_id} is header-only (build_type: none)"
                )
                return True, LibraryType.HEADER_ONLY

            # Check legacy type field
            lib_type = existing_config.get("type")
            if lib_type == "header-only":
                logger.info(f"Using existing configuration: {library_id} is header-only")
                return True, LibraryType.HEADER_ONLY
            elif lib_type == "packaged-headers":
                logger.info(f"Using existing configuration: {library_id} is packaged-headers")
                return True, LibraryType.PACKAGED_HEADERS
            elif lib_type == "static":
                logger.info(f"Using existing configuration: {library_id} is static")
                return True, LibraryType.STATIC
            elif lib_type == "shared":
                logger.info(f"Using existing configuration: {library_id} is shared")
                return True, LibraryType.SHARED
            elif lib_type == "cshared":
                logger.info(f"Using existing configuration: {library_id} is cshared")
                return True, LibraryType.CSHARED

            # If it's type: github with no explicit build_type, it might be header-only by default
            if lib_type == "github" and build_type is None:
                logger.info(
                    f"Using existing configuration: {library_id} is likely header-only "
                    f"(type: github, no build_type)"
                )
                return True, LibraryType.HEADER_ONLY

            # If existing config doesn't have clear type info, continue with detection
            logger.warning(
                f"Could not determine type from existing config for {library_id}, "
                f"falling back to detection"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "repo"

            try:
                # Clone the repository
                result = run_command(
                    ["git", "clone", "--depth", "1", github_url, str(clone_path)], clean_env=False
                )

                if result.returncode != 0:
                    logger.error(f"Failed to clone repository: {result.stderr}")
                    return False, None

                # Check for CMakeLists.txt existence
                cmake_file = clone_path / "CMakeLists.txt"
                has_cmake = cmake_file.exists()

                if has_cmake:
                    # Has CMakeLists.txt, assume it's a packaged-headers library
                    return True, LibraryType.PACKAGED_HEADERS
                else:
                    # No CMakeLists.txt, could be header-only or require manual configuration
                    return True, LibraryType.HEADER_ONLY

            except Exception as e:
                logger.error(f"Error detecting library type: {e}")
                return False, None

    def add_library(self, config: LibraryConfig) -> str | None:
        """
        Add a C++ library using ce_install utilities.

        Args:
            config: Library configuration

        Returns:
            Library ID if successful, None otherwise
        """
        try:
            # Run ce_install cpp-library add command
            subcommand = ["cpp-library", "add", str(config.github_url), config.version]

            if config.library_type:
                subcommand.extend(["--type", config.library_type.value])
                logger.info(f"Adding library with type: {config.library_type.value}")
            else:
                logger.warning("No library type specified for cpp-library add command")

            logger.info(f"Running command: {' '.join(subcommand)}")
            result = run_ce_install_command(subcommand, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                error_output = f"{result.stdout} {result.stderr}".strip()
                logger.error(f"cpp-library add failed: {error_output}")
                return None

            # Parse the output to get the library ID
            output = result.stdout.strip()

            # Look for the library ID in the output
            # Possible formats:
            # - "Added version X to library <library_id>"
            # - "Library '<library_id>' is now available"
            # - "--library <library_id>"

            # Try multiple patterns
            patterns = [
                r"Added version .+ to library (\S+)",
                r"Library '([^']+)' is now available",
                r"--library (\S+)",
                r"Found existing library '([^']+)'",
            ]

            library_id = None
            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    library_id = match.group(1)
                    break

            if library_id:
                logger.info(f"Successfully added C++ library with ID: {library_id}")

                # Debug: Check what was actually written to libraries.yaml
                try:
                    existing_config = check_existing_library_config(
                        str(config.github_url), library_id, self.infra_path
                    )
                    if existing_config:
                        logger.info(f"Library config in libraries.yaml: {existing_config}")
                    else:
                        logger.warning(
                            f"Could not find {library_id} in libraries.yaml after adding"
                        )
                except Exception as e:
                    logger.warning(f"Could not check libraries.yaml: {e}")

                return library_id
            else:
                logger.warning("Could not parse library ID from output, using suggested ID")
                return config.library_id

        except Exception as e:
            logger.error(f"Error adding C++ library: {e}")
            return None

    def generate_properties(self, library_id: str, version: str) -> bool:
        """
        Generate C++ properties file from libraries.yaml.

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

            # Generate Linux properties
            props_file = self.main_path / "etc" / "config" / "c++.amazon.properties"
            subcommand_linux = [
                "cpp-library",
                "generate-linux-props",
                "--input-file",
                str(props_file),
                "--output-file",
                str(props_file),
                "--library",
                library_id,
                "--version",
                version,
            ]

            result = run_ce_install_command(subcommand_linux, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                logger.error(f"generate-linux-props failed: {result.stderr}")
                return False

            logger.info("Successfully generated Linux C++ properties")

            # Also generate Windows properties
            subcommand_windows = ["cpp-library", "generate-windows-props"]

            result = run_ce_install_command(
                subcommand_windows, cwd=self.infra_path, debug=self.debug
            )

            if result.returncode != 0:
                logger.error(f"generate-windows-props failed: {result.stderr}")
                # Don't fail if Windows props generation fails, as it might not be needed
                logger.warning("Windows properties generation failed, but continuing...")

            return True

        except Exception as e:
            logger.error(f"Error generating C++ properties: {e}")
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

    def run_install_test(self, library_id: str, version: str) -> bool:
        """
        Test installing the library using ce_install.

        Args:
            library_id: The library identifier
            version: The library version

        Returns:
            True if installation succeeds, False otherwise
        """
        import re

        try:
            # Check if /opt/compiler-explorer exists
            opt_ce_path = Path("/opt/compiler-explorer")
            if not opt_ce_path.exists():
                logger.error(
                    f"Directory {opt_ce_path} does not exist. Please create it manually with:"
                )
                logger.error("  sudo mkdir -p /opt/compiler-explorer")
                logger.error("  sudo chown -R $USER: /opt/compiler-explorer")
                return False

            # Run ce_install install command with --force
            logger.info(f"Testing installation of {library_id} {version}...")
            install_spec = f"{library_id} {version}"

            result = run_ce_install_command(
                ["install", "--force", install_spec], cwd=self.infra_path, debug=self.debug
            )

            if result.returncode != 0:
                logger.error(f"Installation test failed: {result.stderr}")
                return False

            # Check for staging to destination message in output
            output = result.stdout + result.stderr
            staging_pattern = r"Moving from staging \((.*?)\) to final destination \((.*?)\)"
            staging_match = re.search(staging_pattern, output)

            if not staging_match:
                logger.error(
                    "Installation output did not contain expected 'Moving from staging' message"
                )
                return False

            destination_path = staging_match.group(2)
            logger.info(f"Installation destination: {destination_path}")

            # Check if destination path is in the properties file
            if self.main_path:
                props_file = self.main_path / "etc" / "config" / "c++.amazon.properties"
                if props_file.exists():
                    props_content = props_file.read_text()
                    # Extract the library path from destination
                    # (e.g., /opt/compiler-explorer/libs/nlohmann_json/v3.11.3)
                    # and check if it appears in the properties
                    if destination_path not in props_content:
                        logger.error(
                            f"Inconsistency detected: Installation destination "
                            f"'{destination_path}' not found in properties file"
                        )
                        logger.error(
                            "This suggests the properties file and installation are out of sync"
                        )
                        return False
                else:
                    logger.warning("Properties file not found for verification")

            logger.info("Installation test succeeded")
            return True

        except Exception as e:
            logger.error(f"Error during install test: {e}")
            return False

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
            # Run ce_install list-paths command
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

            # Log the output for debugging
            if self.debug:
                logger.debug(f"list-paths output: {output}")

            # list-paths might have different output format than install
            # Look for the destination path in the output
            destination_path = None

            # Try to parse the list-paths output format
            # Expected format: "libraries/c++/{library} {version}: {path}"
            list_paths_pattern = r"libraries/c\+\+/\S+\s+\S+:\s+(.+)"
            list_match = re.search(list_paths_pattern, output)

            if list_match:
                relative_path = list_match.group(1).strip()
                # Convert relative path to absolute path
                destination_path = f"/opt/compiler-explorer/{relative_path}"
                logger.info(f"Library destination path: {destination_path}")
            else:
                # If no match found, log the output and continue without path check
                logger.warning("Could not parse destination path from list-paths output")
                logger.warning("Skipping path consistency check")
                return True

            # Check if destination path is in the properties file
            if self.main_path:
                props_file = self.main_path / "etc" / "config" / "c++.amazon.properties"
                if props_file.exists():
                    props_content = props_file.read_text()
                    if destination_path not in props_content:
                        logger.error(
                            f"Inconsistency detected: Destination path "
                            f"'{destination_path}' not found in properties file"
                        )
                        logger.error(
                            "This suggests the properties file and library "
                            "configuration are out of sync"
                        )
                        return False
                else:
                    logger.warning("Properties file not found for verification")

            logger.info("Path check succeeded")
            return True

        except Exception as e:
            logger.error(f"Error during path check: {e}")
            return False

"""Handle C library additions to Compiler Explorer."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .library_utils import (
    suggest_library_id_from_github_url,
)
from .models import LibraryConfig, LibraryType
from .subprocess_utils import run_ce_install_command, run_command

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

    def detect_library_type(self, github_url: str) -> tuple[bool, LibraryType | None]:
        """
        Clone repository and detect if it's header-only by checking for CMakeLists.txt.

        Returns:
            Tuple of (is_valid, library_type)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "repo"

            try:
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
                    # Has CMakeLists.txt, assume it's a shared/static library
                    return True, LibraryType.SHARED
                else:
                    # No CMakeLists.txt, likely header-only
                    return True, LibraryType.HEADER_ONLY

            except Exception as e:
                logger.error(f"Error detecting library type: {e}")
                return False, None

    def add_library(self, config: LibraryConfig) -> str | None:
        """
        Add a C library using ce_install cpp-library utilities (C libraries use the same commands).

        Args:
            config: Library configuration

        Returns:
            Library ID if successful, None otherwise
        """
        try:
            # Use cpp-library commands for C libraries since ce_install doesn't have c-library
            subcommand = ["cpp-library", "add", str(config.github_url), config.version]

            if config.library_type:
                subcommand.extend(["--type", config.library_type.value])

            result = run_ce_install_command(subcommand, cwd=self.infra_path, debug=self.debug)

            if result.returncode != 0:
                error_output = f"{result.stdout} {result.stderr}".strip()
                logger.error(f"cpp-library add failed: {error_output}")
                return None

            # Parse the output to get the library ID (same logic as C++)
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
                logger.info(f"Successfully added C library with ID: {library_id}")
                return library_id
            else:
                logger.warning("Could not parse library ID from output, using suggested ID")
                return config.library_id

        except Exception as e:
            logger.error(f"Error adding C library: {e}")
            return None

    def generate_properties(self, library_id: str, version: str) -> bool:
        """
        Generate C properties file from libraries.yaml.

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

            # Generate Linux properties for C libraries using cpp-library commands
            props_file = self.main_path / "etc" / "config" / "c.amazon.properties"
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

            # Check if destination path is in the properties file
            if self.main_path:
                props_file = self.main_path / "etc" / "config" / "c.amazon.properties"
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

"""Handle Fortran library additions to Compiler Explorer."""
from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from .build_tester import (
    BuildTestResult,
    check_fortran_build_test_available,
    run_fortran_build_test,
)
from .constants import FORTRAN_PROPERTIES_PATH, GITHUB_URL_REQUIRED, MAIN_REPO_PATH_REQUIRED
from .library_utils import (
    setup_ce_install as setup_ce_install_shared,
)
from .library_utils import (
    suggest_library_id_from_github_url,
    update_properties_libs_line,
)
from .models import LibraryConfig
from .subprocess_utils import run_ce_install_command, run_command

logger = logging.getLogger(__name__)


class FortranHandler:
    """Handles Fortran library additions to Compiler Explorer infrastructure."""

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

    def validate_fpm_package(self, github_url: str) -> tuple[bool, str | None]:
        """
        Clone repository and validate it has fmp.toml file.
        Returns (is_valid, error_message)
        """
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                clone_path = tmp_path / "repo"

                result = run_command(
                    ["git", "clone", str(github_url), str(clone_path)], debug=self.debug
                )

                if result.returncode != 0:
                    return False, f"Failed to clone repository: {result.stderr}"

                fmp_toml = clone_path / "fpm.toml"
                if not fmp_toml.exists():
                    return (
                        False,
                        "Repository does not contain fpm.toml file (required for Fortran packages)",
                    )

                return True, None

        except Exception as e:
            return False, f"Error validating Fortran package: {e}"

    @staticmethod
    def suggest_library_id_static(github_url: str) -> str:
        """Generate a suggested library ID from GitHub URL"""
        return suggest_library_id_from_github_url(github_url)

    def suggest_library_id(self, github_url: str) -> str:
        """Generate a suggested library ID from GitHub URL"""
        return self.suggest_library_id_static(github_url)

    def add_library(self, config: LibraryConfig) -> str | None:
        """
        Add Fortran library to libraries.yaml using ce_install.
        Returns library_id if successful, None otherwise.
        """
        try:
            if not config.github_url:
                raise ValueError(GITHUB_URL_REQUIRED.format("Fortran"))

            is_valid, error_msg = self.validate_fpm_package(config.github_url)
            if not is_valid:
                logger.error(f"Fortran package validation failed: {error_msg}")
                return None

            library_id = config.library_id or self.suggest_library_id(config.github_url)

            result = run_ce_install_command(
                ["fortran-library", "add", str(config.github_url), config.version],
                cwd=self.infra_path,
                debug=self.debug,
            )

            if result.returncode != 0:
                logger.error(f"Failed to add Fortran library: {result.stderr}")
                return None

            logger.info(f"Successfully added Fortran library {library_id}")
            return library_id

        except Exception as e:
            logger.error(f"Error adding Fortran library: {e}")
            return None

    def update_fortran_properties(self, library_id: str, config: LibraryConfig) -> bool:
        """
        Update the main repo's fortran.amazon.properties file with the new library.
        Returns True if successful, False otherwise.
        """
        if not self.main_path:
            logger.error(MAIN_REPO_PATH_REQUIRED)
            return False

        try:
            props_file = self.main_path / FORTRAN_PROPERTIES_PATH

            if not props_file.exists():
                logger.error(f"Fortran properties file not found: {props_file}")
                return False

            with open(props_file, encoding="utf-8") as f:
                content = f.read()

            version_key = re.sub(r"[^a-z0-9]", "", config.version.lower())

            library_props = []
            library_props.append(f"libs.{library_id}.name={library_id}")
            library_props.append(f"libs.{library_id}.url={config.github_url}")

            if hasattr(config, "description") and config.description:
                library_props.append(f"libs.{library_id}.description={config.description}")

            library_props.append(f"libs.{library_id}.staticliblink={library_id}")
            library_props.append(f"libs.{library_id}.versions={version_key}")
            library_props.append(f"libs.{library_id}.packagedheaders=true")
            library_props.append(
                f"libs.{library_id}.versions.{version_key}.version={config.version}"
            )

            content = update_properties_libs_line(content, library_id)

            # Find insertion point before tools section
            tools_section_match = re.search(
                r"\n(#{33}\n#{33}\n# Installed tools)",
                content,
            )

            if tools_section_match:
                insertion_point = tools_section_match.start()
                new_content = (
                    content[:insertion_point]
                    + "\n"
                    + "\n".join(library_props)
                    + "\n\n"
                    + content[insertion_point:]
                )
            else:
                new_content = content + "\n\n" + "\n".join(library_props) + "\n"

            with open(props_file, "w", encoding="utf-8") as f:
                f.write(new_content)

            logger.info(f"Successfully updated {props_file.name}")
            return True

        except Exception as e:
            logger.error(f"Error updating Fortran properties: {e}")
            return False

    def is_build_test_available(self) -> tuple[bool, str]:
        """
        Check if Fortran build testing is available (Fortran compiler installed).

        Returns:
            Tuple of (available, message)
        """
        return check_fortran_build_test_available(self.infra_path, self.debug)

    def run_build_test(
        self,
        library_id: str,
        version: str,
        compiler_id: str | None = None,
    ) -> BuildTestResult:
        """
        Test building the Fortran library using ce_install build command.

        Fortran libraries using FPM are compiled during the build step,
        producing static libraries (.a) and module files (.mod).

        Args:
            library_id: The library identifier
            version: The library version
            compiler_id: Specific Fortran compiler ID to use (auto-detected if None)

        Returns:
            BuildTestResult with success status, message, and artifact information
        """
        return run_fortran_build_test(
            infra_path=self.infra_path,
            library_id=library_id,
            version=version,
            compiler_id=compiler_id,
            debug=self.debug,
        )

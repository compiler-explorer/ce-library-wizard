"""Handle C++ library additions to Compiler Explorer."""
import logging
import tempfile
from pathlib import Path
from typing import Optional, Tuple

from .models import LibraryConfig, LibraryType
from .subprocess_utils import run_make_command, run_ce_install_command

logger = logging.getLogger(__name__)


class CppHandler:
    """Handles C++ library additions to Compiler Explorer infrastructure."""
    
    def __init__(self, infra_path: Path, main_path: Path = None, setup_ce_install: bool = True, debug: bool = False):
        self.infra_path = infra_path
        self.main_path = main_path
        self.debug = debug
        if setup_ce_install:
            self.setup_ce_install()
    
    def setup_ce_install(self) -> bool:
        """Ensure ce_install is available"""
        try:
            # Need to run make ce first
            logger.info("Setting up ce_install...")
            
            result = run_make_command(
                "ce",
                cwd=self.infra_path,
                debug=self.debug
            )
            
            if result.returncode != 0:
                logger.warning(f"Setup command failed with return code: {result.returncode}")

            return True
            
        except Exception as e:
            raise RuntimeError(f"Error setting up ce_install: {e}")
    
    def detect_library_type(self, github_url: str) -> Tuple[bool, Optional[LibraryType]]:
        """
        Clone repository and detect if it's header-only by checking for CMakeLists.txt.
        
        Returns:
            Tuple of (is_valid, library_type)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            clone_path = Path(tmpdir) / "repo"
            
            try:
                # Clone the repository  
                from .subprocess_utils import run_command
                result = run_command(
                    ["git", "clone", "--depth", "1", github_url, str(clone_path)],
                    clean_env=False
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
    
    def add_library(self, config: LibraryConfig) -> Optional[str]:
        """
        Add a C++ library using ce_install utilities.
        
        Args:
            config: Library configuration
            
        Returns:
            Library ID if successful, None otherwise
        """
        try:
            # Run ce_install cpp-library add command
            subcommand = [
                "cpp-library", "add",
                str(config.github_url),
                config.version
            ]
            
            if config.library_type:
                subcommand.extend(["--type", config.library_type.value])
            
            result = run_ce_install_command(
                subcommand,
                cwd=self.infra_path,
                debug=self.debug
            )

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
            import re
            
            # Try multiple patterns
            patterns = [
                r"Added version .+ to library (\S+)",
                r"Library '([^']+)' is now available",
                r"--library (\S+)",
                r"Found existing library '([^']+)'"
            ]
            
            library_id = None
            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    library_id = match.group(1)
                    break
            
            if library_id:
                logger.info(f"Successfully added C++ library with ID: {library_id}")
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
                "cpp-library", "generate-linux-props",
                "--input-file", str(props_file),
                "--output-file", str(props_file),
                "--library", library_id,
                "--version", version
            ]
            
            result = run_ce_install_command(
                subcommand_linux,
                cwd=self.infra_path,
                debug=self.debug
            )
            
            if result.returncode != 0:
                logger.error(f"generate-linux-props failed: {result.stderr}")
                return False
                
            logger.info("Successfully generated Linux C++ properties")
            
            # Also generate Windows properties
            subcommand_windows = ["cpp-library", "generate-windows-props"]
            
            result = run_ce_install_command(
                subcommand_windows,
                cwd=self.infra_path,
                debug=self.debug
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
        import re
        # Must be lowercase letters, numbers, and underscores only
        # Must start with a letter
        pattern = r'^[a-z][a-z0-9_]*$'
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
        # Extract repo name from URL
        parts = github_url.rstrip('/').split('/')
        if len(parts) >= 2:
            repo_name = parts[-1]
            # Remove .git suffix if present
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]
            
            # Convert to lowercase and replace non-alphanumeric with underscores
            import re
            library_id = re.sub(r'[^a-z0-9]+', '_', repo_name.lower())
            # Remove leading/trailing underscores
            library_id = library_id.strip('_')
            # Ensure it starts with a letter
            if library_id and not library_id[0].isalpha():
                library_id = 'lib_' + library_id
            
            return library_id or 'new_library'
        
        return 'new_library'
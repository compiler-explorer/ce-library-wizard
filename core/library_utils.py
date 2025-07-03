"""Shared utilities for library handlers."""
import logging
import re
from pathlib import Path

from .subprocess_utils import run_make_command

logger = logging.getLogger(__name__)


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

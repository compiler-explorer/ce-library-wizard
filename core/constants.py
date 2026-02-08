"""Shared constants for the CE Library Wizard."""

# PR and Git Messages
PR_FOOTER = "\n\n---\n_PR created with [ce-lib-wizard](https://github.com/compiler-explorer/ce-library-wizard)_"

# Authentication Messages
AUTH_WARNING_NO_GITHUB = (
    "\n⚠️  No GitHub authentication found. Changes committed locally but not pushed."
)
AUTH_HELP_MESSAGE = """To push changes and create PRs, use one of these options:
  - Install and authenticate GitHub CLI: gh auth login
  - Set GITHUB_TOKEN environment variable
  - Use --oauth flag for browser-based authentication"""

# UI Messages
CHANGES_HEADER = "=" * 60
CHANGES_TITLE = "CHANGES TO BE COMMITTED:"
REPO_SEPARATOR = "-" * 60
NO_CHANGES_MESSAGE = "No changes detected"
CHANGES_CANCELLED = "Changes cancelled."
CONFIRM_CHANGES_PROMPT = "\nDo you want to proceed with these changes?"

# Success Messages
SUCCESS_CREATED_PR = "\n✓ Created PR:"
SUCCESS_MODIFIED_FILES = "✓ Modified libraries.yaml and updated properties"

# File Paths
C_PROPERTIES_PATH = "etc/config/c.amazon.properties"
CPP_PROPERTIES_PATH = "etc/config/c++.amazon.properties"
FORTRAN_PROPERTIES_PATH = "etc/config/fortran.amazon.properties"
RUST_PROPERTIES_PATH = "etc/config/rust.amazon.properties"
GO_PROPERTIES_PATH = "etc/config/go.amazon.properties"
LIBRARIES_YAML_PATH = "bin/yaml/libraries.yaml"

# Validation Messages
GITHUB_URL_REQUIRED = "GitHub URL is required for {} libraries"
MAIN_REPO_PATH_REQUIRED = "Main repository path not provided"

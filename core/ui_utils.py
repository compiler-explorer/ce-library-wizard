"""Shared UI utilities for the CE Library Wizard CLI."""
import click

from .constants import (
    AUTH_HELP_MESSAGE,
    AUTH_WARNING_NO_GITHUB,
    CHANGES_CANCELLED,
    CHANGES_HEADER,
    CHANGES_TITLE,
    CONFIRM_CHANGES_PROMPT,
    NO_CHANGES_MESSAGE,
    REPO_SEPARATOR,
    SUCCESS_CREATED_PR,
)


def display_authentication_warning():
    """Display standard authentication warning message."""
    click.echo(AUTH_WARNING_NO_GITHUB)
    click.echo(AUTH_HELP_MESSAGE)


def display_changes_and_confirm(
    git_mgr, infra_repo_path, main_repo_path, infra_repo_name, main_repo_name
):
    """
    Display git changes for both repositories and ask for confirmation.

    Args:
        git_mgr: GitManager instance
        infra_repo_path: Path to infra repository
        main_repo_path: Path to main repository
        infra_repo_name: Display name for infra repository
        main_repo_name: Display name for main repository

    Returns:
        bool: True if user confirms, False if cancelled
    """
    click.echo("\n" + CHANGES_HEADER)
    click.echo(CHANGES_TITLE)
    click.echo(CHANGES_HEADER)

    # Show infra repo diff
    click.echo(f"\n📁 Repository: {infra_repo_name}")
    click.echo(REPO_SEPARATOR)
    infra_diff = git_mgr.get_diff(infra_repo_path)
    if infra_diff:
        click.echo(infra_diff)
    else:
        click.echo(NO_CHANGES_MESSAGE)

    # Show main repo diff
    click.echo(f"\n📁 Repository: {main_repo_name}")
    click.echo(REPO_SEPARATOR)
    main_diff = git_mgr.get_diff(main_repo_path)
    if main_diff:
        click.echo(main_diff)
    else:
        click.echo(NO_CHANGES_MESSAGE)

    click.echo("\n" + CHANGES_HEADER)

    # Ask for confirmation
    if not click.confirm(CONFIRM_CHANGES_PROMPT):
        click.echo(CHANGES_CANCELLED)
        return False
    return True


def display_pr_success(repo_type: str, pr_url: str, is_first: bool = True):
    """
    Display PR creation success message.

    Args:
        repo_type: Type of repository (e.g., "Infra", "Main")
        pr_url: URL of the created PR
        is_first: Whether this is the first PR being displayed
    """
    if is_first:
        click.echo(SUCCESS_CREATED_PR)
    click.echo(f"  - {repo_type}: {pr_url}")


def create_commit_message(language: str, library_name: str, version: str) -> str:
    """
    Create a standardized commit message.

    Args:
        language: Programming language (e.g., "Rust", "C++", "Fortran")
        library_name: Name of the library
        version: Version of the library

    Returns:
        Formatted commit message
    """
    return f"Add {language} library {library_name} v{version}"

#!/usr/bin/env python3
import logging
import platform
import traceback

import click

from cli.questions import ask_library_questions
from core.cpp_handler import CppHandler
from core.file_modifications import update_rust_properties
from core.fortran_handler import FortranHandler
from core.git_operations import GitManager
from core.models import Language, LibraryConfig
from core.rust_handler import RustLibraryHandler


def process_cpp_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    install_test: bool = False,
):
    """Process a C++ library addition"""
    click.echo(f"\nProcessing C++ library: {config.library_id} v{config.version}")

    with GitManager(github_token, debug=debug) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        # Create feature branches
        branch_name = f"add-cpp-{config.library_id}-{config.version}".replace(".", "-")
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        # Handle C++ specific operations
        click.echo("Running ce_install to add C++ library...")
        cpp_handler = CppHandler(infra_repo_path, main_repo_path, debug=debug)

        try:
            # Add library to libraries.yaml
            library_id = cpp_handler.add_library(config)
            if not library_id:
                click.echo("❌ Failed to add library to libraries.yaml", err=True)
                return

            # Generate C++ properties
            click.echo("Generating C++ properties...")
            if not cpp_handler.generate_properties(library_id, config.version):
                click.echo("❌ Failed to generate C++ properties", err=True)
                return

            click.echo("✓ Modified libraries.yaml and generated properties")

            # Check library paths
            if install_test:
                # Run install test if requested (non-Windows only)
                if platform.system() == "Windows":
                    click.echo("\n⚠️  Install test is not supported on Windows")
                else:
                    click.echo("\n🧪 Running install test...")
                    if not cpp_handler.run_install_test(library_id, config.version):
                        click.echo("❌ Install test failed. Aborting.", err=True)
                        return
                    click.echo("✓ Install test passed")
            else:
                # Just check paths without installing
                click.echo("\n🔍 Checking library paths...")
                if not cpp_handler.check_library_paths(library_id, config.version):
                    click.echo("❌ Path check failed. Aborting.", err=True)
                    return
                click.echo("✓ Path check passed")

            # TODO: Update main repo files for C++
            # This will need implementation once we know the exact file structure

            # Show diffs if verify flag is set
            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                # Show infra repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                # Show main repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                # Ask for confirmation
                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

            # Commit changes
            commit_msg = f"Add C++ library {config.library_id} v{config.version}"

            infra_committed = git_mgr.commit_changes(infra_repo_path, commit_msg)
            main_committed = git_mgr.commit_changes(main_repo_path, commit_msg)

            if not infra_committed and not main_committed:
                click.echo("⚠️  Library version already exists - no changes to commit.")
                return

            if github_token:
                # Only proceed with pushing and PRs if we have commits
                if infra_committed or main_committed:
                    # Push branches and create PRs
                    click.echo("\nPushing branches...")
                    if infra_committed:
                        git_mgr.push_branch(infra_repo_path, infra_branch)
                    if main_committed:
                        git_mgr.push_branch(main_repo_path, main_branch)

                    click.echo("\nCreating pull requests...")
                    pr_body = (
                        f"This PR adds the C++ library **{config.library_id}** "
                        f"version {config.version} to Compiler Explorer.\n\n"
                    )
                    pr_body += f"- GitHub URL: {config.github_url}\n"
                    library_type = config.library_type.value if config.library_type else "Unknown"
                    if library_type != "Unknown":
                        pr_body += f"- Library Type: {library_type}"

                    if infra_committed:
                        infra_pr_body = (
                            pr_body
                            + "\n\n---\n_PR created with [ce-lib-wizard](https://github.com/compiler-explorer/ce-lib-wizard)_"
                        )
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += "\n\n---\n_PR created with [ce-lib-wizard](https://github.com/compiler-explorer/ce-lib-wizard)_"

                        main_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_MAIN_REPO,
                            main_branch,
                            commit_msg,
                            main_pr_body,
                        )
                        if not infra_committed:
                            click.echo("\n✓ Created PR:")
                        click.echo(f"  - Main: {main_pr_url}")
                else:
                    click.echo("\n⚠️  No changes to push - skipping PR creation.")
            else:
                click.echo(
                    "\n⚠️  No GitHub authentication found. Changes committed locally but not pushed."
                )
                click.echo("To push changes and create PRs, use one of these options:")
                click.echo("  - Install and authenticate GitHub CLI: gh auth login")
                click.echo("  - Set GITHUB_TOKEN environment variable")
                click.echo("  - Use --oauth flag for browser-based authentication")

        except Exception as e:
            click.echo(f"\n❌ Error processing C++ library: {e}", err=True)
            raise


def process_rust_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
):
    """Process a Rust library addition"""
    click.echo(f"\nProcessing Rust crate: {config.name} v{config.version}")

    with GitManager(github_token, debug=debug) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        # Create feature branches
        branch_name = f"add-rust-{config.name}-{config.version}".replace(".", "-")
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        # Handle Rust-specific operations
        click.echo("Running ce_install to add crate...")
        rust_handler = RustLibraryHandler(infra_repo_path, debug=debug)

        try:
            libraries_yaml_path, new_props_content = rust_handler.process_rust_library(config)
            click.echo(f"✓ Modified {libraries_yaml_path.name}")

            # Update main repo with new properties
            click.echo("Updating rust.amazon.properties...")
            props_file = update_rust_properties(main_repo_path, new_props_content)
            click.echo(f"✓ Modified {props_file.name}")

            # Show diffs if verify flag is set
            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                # Show infra repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                # Show main repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                # Ask for confirmation
                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

            # Commit changes
            commit_msg = f"Add Rust crate {config.name} v{config.version}"

            git_mgr.commit_changes(infra_repo_path, commit_msg)
            git_mgr.commit_changes(main_repo_path, commit_msg)

            if github_token:
                # Push branches and create PRs
                click.echo("\nPushing branches...")
                git_mgr.push_branch(infra_repo_path, infra_branch)
                git_mgr.push_branch(main_repo_path, main_branch)

                click.echo("\nCreating pull requests...")
                pr_body = (
                    f"This PR adds the Rust crate **{config.name}** "
                    f"version {config.version} to Compiler Explorer."
                )

                infra_pr_url = git_mgr.create_pull_request(
                    GitManager.CE_INFRA_REPO, infra_branch, commit_msg, pr_body
                )

                main_pr_url = git_mgr.create_pull_request(
                    GitManager.CE_MAIN_REPO,
                    main_branch,
                    commit_msg,
                    pr_body + f"\n\nRelated PR: {infra_pr_url}",
                )

                click.echo("\n✓ Created PRs:")
                click.echo(f"  - Infra: {infra_pr_url}")
                click.echo(f"  - Main: {main_pr_url}")
            else:
                click.echo(
                    "\n⚠️  No GitHub authentication found. Changes committed locally but not pushed."
                )
                click.echo("To push changes and create PRs, use one of these options:")
                click.echo("  - Install and authenticate GitHub CLI: gh auth login")
                click.echo("  - Set GITHUB_TOKEN environment variable")
                click.echo("  - Use --oauth flag for browser-based authentication")

        except Exception as e:
            click.echo(f"\n❌ Error processing Rust library: {e}", err=True)
            raise


def process_fortran_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
):
    """Process a Fortran library addition"""
    click.echo(f"\nProcessing Fortran library: {config.library_id or 'unknown'} v{config.version}")

    with GitManager(github_token, debug=debug) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        # Create feature branches
        library_name = config.library_id or FortranHandler.suggest_library_id_static(
            config.github_url
        )
        branch_name = f"add-fortran-{library_name}-{config.version}".replace(".", "-")
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        # Handle Fortran specific operations
        click.echo("Running ce_install to add Fortran library...")
        fortran_handler = FortranHandler(infra_repo_path, main_repo_path, debug=debug)

        try:
            # Add library to libraries.yaml
            library_id = fortran_handler.add_library(config)
            if not library_id:
                click.echo("❌ Failed to add library to libraries.yaml", err=True)
                return

            # Update main repo with library properties
            click.echo("Updating fortran.amazon.properties...")
            config.library_id = library_id  # Ensure library_id is set
            if not fortran_handler.update_fortran_properties(library_id, config):
                click.echo("❌ Failed to update Fortran properties", err=True)
                return

            click.echo("✓ Modified libraries.yaml and updated properties")

            # Show diffs if verify flag is set
            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                # Show infra repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                # Show main repo diff
                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                # Ask for confirmation
                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

            # Commit changes
            commit_msg = f"Add Fortran library {library_id} v{config.version}"

            infra_committed = git_mgr.commit_changes(infra_repo_path, commit_msg)
            main_committed = git_mgr.commit_changes(main_repo_path, commit_msg)

            if not infra_committed and not main_committed:
                click.echo("⚠️  Library version already exists - no changes to commit.")
                return

            if github_token:
                # Only proceed with pushing and PRs if we have commits
                if infra_committed or main_committed:
                    # Push branches and create PRs
                    click.echo("\nPushing branches...")
                    if infra_committed:
                        git_mgr.push_branch(infra_repo_path, infra_branch)
                    if main_committed:
                        git_mgr.push_branch(main_repo_path, main_branch)

                    click.echo("\nCreating pull requests...")
                    pr_body = (
                        f"This PR adds the Fortran library **{library_id}** "
                        f"version {config.version} to Compiler Explorer.\n\n"
                    )
                    pr_body += f"- GitHub URL: {config.github_url}\n"
                    pr_body += "- Package Manager: FPM (Fortran Package Manager)"

                    if infra_committed:
                        infra_pr_body = (
                            pr_body
                            + "\n\n---\n_PR created with [ce-lib-wizard](https://github.com/compiler-explorer/ce-lib-wizard)_"
                        )
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += "\n\n---\n_PR created with [ce-lib-wizard](https://github.com/compiler-explorer/ce-lib-wizard)_"

                        main_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_MAIN_REPO,
                            main_branch,
                            commit_msg,
                            main_pr_body,
                        )
                        if not infra_committed:
                            click.echo("\n✓ Created PR:")
                        click.echo(f"  - Main: {main_pr_url}")
                else:
                    click.echo("\n⚠️  No changes to push - skipping PR creation.")
            else:
                click.echo(
                    "\n⚠️  No GitHub authentication found. Changes committed locally but not pushed."
                )
                click.echo("To push changes and create PRs, use one of these options:")
                click.echo("  - Install and authenticate GitHub CLI: gh auth login")
                click.echo("  - Set GITHUB_TOKEN environment variable")
                click.echo("  - Use --oauth flag for browser-based authentication")

        except Exception as e:
            click.echo(f"\n❌ Error processing Fortran library: {e}", err=True)
            raise


@click.command()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--github-token", envvar="GITHUB_TOKEN", help="GitHub token for creating PRs")
@click.option("--oauth", is_flag=True, help="Authenticate via browser using GitHub OAuth")
@click.option("--verify", is_flag=True, help="Show git diff of changes before committing")
@click.option("--install-test", is_flag=True, help="Test library installation (non-Windows only)")
@click.option(
    "--lang",
    type=click.Choice(["c", "c++", "rust", "fortran", "java", "kotlin"], case_sensitive=False),
    help="Language for the library",
)
@click.option("--lib", help="Library name (for Rust) or GitHub URL (for other languages)")
@click.option("--ver", help="Library version")
def main(
    debug: bool,
    github_token: str | None,
    oauth: bool,
    verify: bool,
    install_test: bool,
    lang: str | None,
    lib: str | None,
    ver: str | None,
):
    """CLI tool to add libraries to Compiler Explorer"""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(name)s: %(message)s")

    click.echo("Welcome to CE Library Wizard!")
    click.echo("This tool will help you add a new library to Compiler Explorer.\n")

    try:
        # Try to get GitHub token if not provided
        if not github_token:
            from core.github_auth import get_github_token_via_gh_cli, get_github_token_via_oauth

            # First try GitHub CLI
            github_token = get_github_token_via_gh_cli()
            if github_token:
                click.echo("✅ Using GitHub CLI authentication")
            elif oauth:
                # Only try OAuth if explicitly requested
                github_token = get_github_token_via_oauth()
                if not github_token:
                    click.echo("❌ Failed to authenticate. Exiting.", err=True)
                    return 1

        # If all parameters provided, skip interactive questions
        if lang and lib and ver:
            # Map language strings to enum values
            lang_map = {
                "c": Language.C,
                "c++": Language.CPP,
                "rust": Language.RUST,
                "fortran": Language.FORTRAN,
                "java": Language.JAVA,
                "kotlin": Language.KOTLIN,
            }

            language = lang_map[lang.lower()]

            if language == Language.RUST:
                config = LibraryConfig(language=language, name=lib, version=ver)
            else:
                # For non-Rust, lib should be a GitHub URL
                config = LibraryConfig(language=language, github_url=lib, version=ver)

                # For C++ and Fortran, we need to set library_id
                if language == Language.CPP:
                    from core.cpp_handler import CppHandler

                    config.library_id = CppHandler.suggest_library_id_static(lib)
                elif language == Language.FORTRAN:
                    config.library_id = FortranHandler.suggest_library_id_static(lib)
        else:
            # Interactive mode
            config = ask_library_questions()

        if debug:
            click.echo("\nLibrary Configuration:")
            click.echo(config.model_dump_json(indent=2))

        if config.is_rust():
            process_rust_library(config, github_token, verify, debug)
        elif config.language == Language.CPP:
            process_cpp_library(config, github_token, verify, debug, install_test)
        elif config.language == Language.FORTRAN:
            process_fortran_library(config, github_token, verify, debug)
        else:
            click.echo("\n⚠️  This language is not yet implemented.")
            click.echo("Currently only Rust, C++, and Fortran library additions are supported.")

    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return 1
    except Exception as e:
        if debug:
            traceback.print_exc()
        click.echo(f"\nError: {e}", err=True)
        return 1


if __name__ == "__main__":
    main()

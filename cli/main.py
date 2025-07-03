#!/usr/bin/env python3
import logging
import platform
import traceback

import click

from cli.questions import ask_library_questions
from core.c_handler import CHandler
from core.constants import PR_FOOTER, SUCCESS_MODIFIED_FILES
from core.cpp_handler import CppHandler
from core.file_modifications import update_rust_properties
from core.fortran_handler import FortranHandler
from core.git_operations import GitManager
from core.github_auth import get_github_token_via_gh_cli, get_github_token_via_oauth
from core.models import Language, LibraryConfig, LibraryType
from core.rust_handler import RustLibraryHandler
from core.subprocess_utils import run_ce_install_command
from core.ui_utils import (
    display_authentication_warning,
)


def create_single_version_config(config: LibraryConfig, version: str) -> LibraryConfig:
    """Create a new config with a single version from a multi-version config"""
    config_dict = config.model_dump()
    config_dict["version"] = version
    return LibraryConfig(**config_dict)


def process_cpp_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    install_test: bool = False,
    keep_temp: bool = False,
):
    """Process a C++ library addition"""
    click.echo(f"\nProcessing C++ library: {config.library_id} v{config.version}")

    with GitManager(github_token, debug=debug, keep_temp=keep_temp) as git_mgr:
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

                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

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
                        infra_pr_body = pr_body + PR_FOOTER
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += PR_FOOTER

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
                display_authentication_warning()

        except Exception as e:
            click.echo(f"\n❌ Error processing C++ library: {e}", err=True)
            raise


def process_rust_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    keep_temp: bool = False,
):
    """Process a Rust library addition"""
    click.echo(f"\nProcessing Rust crate: {config.name} v{config.version}")

    with GitManager(github_token, debug=debug, keep_temp=keep_temp) as git_mgr:
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

                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

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
                display_authentication_warning()

        except Exception as e:
            click.echo(f"\n❌ Error processing Rust library: {e}", err=True)
            raise


def process_c_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    install_test: bool = False,
    keep_temp: bool = False,
):
    """Process a C library addition"""
    click.echo(f"\nProcessing C library: {config.library_id} v{config.version}")

    with GitManager(github_token, debug=debug, keep_temp=keep_temp) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        # Create feature branches
        branch_name = f"add-c-{config.library_id}-{config.version}".replace(".", "-")
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        # Handle C specific operations
        click.echo("Running ce_install to add C library...")
        c_handler = CHandler(infra_repo_path, main_repo_path, debug=debug)

        try:
            # Add library to libraries.yaml
            library_id = c_handler.add_library(config)
            if not library_id:
                click.echo("❌ Failed to add library to libraries.yaml", err=True)
                return

            # Generate C properties
            click.echo("Generating C properties...")
            if not c_handler.generate_properties(library_id, config.version):
                click.echo("❌ Failed to generate C properties", err=True)
                return

            click.echo("✓ Modified libraries.yaml and generated properties")

            # Check library paths (no install test for C libraries yet)
            click.echo("\n🔍 Checking library paths...")
            if not c_handler.check_library_paths(library_id, config.version):
                click.echo("❌ Path check failed. Aborting.", err=True)
                return
            click.echo("✓ Path check passed")

            # Show diffs if verify flag is set
            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

            # Commit changes
            commit_msg = f"Add C library {config.library_id} v{config.version}"

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
                        f"This PR adds the C library **{config.library_id}** "
                        f"version {config.version} to Compiler Explorer.\n\n"
                    )
                    pr_body += f"- GitHub URL: {config.github_url}\n"
                    library_type = config.library_type.value if config.library_type else "Unknown"
                    if library_type != "Unknown":
                        pr_body += f"- Library Type: {library_type}"

                    if infra_committed:
                        infra_pr_body = pr_body + PR_FOOTER
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += PR_FOOTER

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
                display_authentication_warning()

        except Exception as e:
            click.echo(f"\n❌ Error processing C library: {e}", err=True)
            raise


def process_top_rust_crates(
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    keep_temp: bool = False,
):
    """Process adding the top 100 Rust crates"""
    click.echo("\nProcessing top 100 Rust crates...")
    click.echo("⚠️  This will add a large number of crates to Compiler Explorer.")

    if not click.confirm("Do you want to proceed?"):
        click.echo("Operation cancelled.")
        return

    with GitManager(github_token, debug=debug, keep_temp=keep_temp) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        # Create feature branches
        branch_name = "add-top-100-rust-crates"
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        try:
            # Use existing RustLibraryHandler for setup and properties generation
            click.echo("Setting up ce_install environment...")
            rust_handler = RustLibraryHandler(infra_repo_path, debug=debug)
            rust_handler.setup_ce_install()

            # Run ce_install add-top-rust-crates command
            click.echo("Running ce_install to add top 100 Rust crates...")
            result = run_ce_install_command(
                ["add-top-rust-crates"], cwd=infra_repo_path, debug=debug
            )

            if result.returncode != 0:
                click.echo("❌ Failed to add top Rust crates", err=True)
                click.echo(f"Error: {result.stderr}", err=True)
                return

            click.echo("✓ Successfully added top 100 Rust crates to libraries.yaml")

            # Generate Rust properties using existing handler
            click.echo("Generating Rust properties...")
            new_props_content = rust_handler.generate_rust_props()

            # Update main repo with new properties
            click.echo("Updating rust.amazon.properties...")
            props_file = update_rust_properties(main_repo_path, new_props_content)
            click.echo(f"✓ Modified {props_file.name}")

            # Show diffs if verify flag is set
            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    # Truncate very long diffs
                    if len(infra_diff) > 5000:
                        lines = infra_diff.split("\n")
                        click.echo("\n".join(lines[:50]))
                        click.echo(f"\n... [Diff truncated - {len(lines)-50} more lines] ...")
                    else:
                        click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    # Truncate very long diffs
                    if len(main_diff) > 5000:
                        lines = main_diff.split("\n")
                        click.echo("\n".join(lines[:50]))
                        click.echo(f"\n... [Diff truncated - {len(lines)-50} more lines] ...")
                    else:
                        click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

            # Commit changes
            commit_msg = "Add top 100 Rust crates to Compiler Explorer"

            infra_committed = git_mgr.commit_changes(infra_repo_path, commit_msg)
            main_committed = git_mgr.commit_changes(main_repo_path, commit_msg)

            if not infra_committed and not main_committed:
                click.echo("⚠️  No changes to commit.")
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
                        "This PR adds the **top 100 Rust crates** to Compiler Explorer.\n\n"
                        "This bulk addition includes the most popular crates from crates.io "
                        "to provide better library support for Rust users."
                    )

                    if infra_committed:
                        infra_pr_body = pr_body + PR_FOOTER
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += PR_FOOTER

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
                display_authentication_warning()

        except Exception as e:
            click.echo(f"\n❌ Error processing top Rust crates: {e}", err=True)
            raise


def process_fortran_library(
    config: LibraryConfig,
    github_token: str | None = None,
    verify: bool = False,
    debug: bool = False,
    keep_temp: bool = False,
):
    """Process a Fortran library addition"""
    click.echo(f"\nProcessing Fortran library: {config.library_id or 'unknown'} v{config.version}")

    with GitManager(github_token, debug=debug, keep_temp=keep_temp) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()

        library_name = config.library_id or FortranHandler.suggest_library_id_static(
            config.github_url
        )
        branch_name = f"add-fortran-{library_name}-{config.version}".replace(".", "-")
        infra_branch = f"{branch_name}-infra"
        main_branch = f"{branch_name}-main"
        git_mgr.create_branch(infra_repo_path, infra_branch)
        git_mgr.create_branch(main_repo_path, main_branch)

        click.echo("Running ce_install to add Fortran library...")
        fortran_handler = FortranHandler(infra_repo_path, main_repo_path, debug=debug)

        try:
            library_id = fortran_handler.add_library(config)
            if not library_id:
                click.echo("❌ Failed to add library to libraries.yaml", err=True)
                return

            click.echo("Updating fortran.amazon.properties...")
            config.library_id = library_id
            if not fortran_handler.update_fortran_properties(library_id, config):
                click.echo("❌ Failed to update Fortran properties", err=True)
                return

            click.echo(SUCCESS_MODIFIED_FILES)

            if verify:
                click.echo("\n" + "=" * 60)
                click.echo("CHANGES TO BE COMMITTED:")
                click.echo("=" * 60)

                click.echo(f"\n📁 Repository: {GitManager.CE_INFRA_REPO}")
                click.echo("-" * 60)
                infra_diff = git_mgr.get_diff(infra_repo_path)
                if infra_diff:
                    click.echo(infra_diff)
                else:
                    click.echo("No changes detected")

                click.echo(f"\n📁 Repository: {GitManager.CE_MAIN_REPO}")
                click.echo("-" * 60)
                main_diff = git_mgr.get_diff(main_repo_path)
                if main_diff:
                    click.echo(main_diff)
                else:
                    click.echo("No changes detected")

                click.echo("\n" + "=" * 60)

                if not click.confirm("\nDo you want to proceed with these changes?"):
                    click.echo("Changes cancelled.")
                    return

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
                        infra_pr_body = pr_body + PR_FOOTER
                        infra_pr_url = git_mgr.create_pull_request(
                            GitManager.CE_INFRA_REPO, infra_branch, commit_msg, infra_pr_body
                        )
                        click.echo("\n✓ Created PR:")
                        click.echo(f"  - Infra: {infra_pr_url}")

                    if main_committed:
                        main_pr_body = pr_body
                        if infra_committed:
                            main_pr_body += f"\n\nRelated PR: {infra_pr_url}"
                        main_pr_body += PR_FOOTER

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
                display_authentication_warning()

        except Exception as e:
            click.echo(f"\n❌ Error processing Fortran library: {e}", err=True)
            raise


@click.command()
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--github-token", envvar="GITHUB_TOKEN", help="GitHub token for creating PRs")
@click.option("--oauth", is_flag=True, help="Authenticate via browser using GitHub OAuth")
@click.option("--verify", is_flag=True, help="Show git diff of changes before committing")
@click.option("--install-test", is_flag=True, help="Test library installation (non-Windows only)")
@click.option("--keep-temp", is_flag=True, help="Keep temporary directories for debugging")
@click.option("--top-rust-crates", is_flag=True, help="Add the top 100 Rust crates")
@click.option(
    "--lang",
    type=click.Choice(["c", "c++", "rust", "fortran"], case_sensitive=False),
    help="Language for the library",
)
@click.option("--lib", help="Library name (for Rust) or GitHub URL (for other languages)")
@click.option("--ver", help="Library version (comma-separated for multiple versions)")
@click.option(
    "--type",
    type=click.Choice(
        ["header-only", "packaged-headers", "static", "shared", "cshared"], case_sensitive=False
    ),
    help="Library type (for C/C++ libraries)",
)
def main(
    debug: bool,
    github_token: str | None,
    oauth: bool,
    verify: bool,
    install_test: bool,
    keep_temp: bool,
    top_rust_crates: bool,
    lang: str | None,
    lib: str | None,
    ver: str | None,
    type: str | None,
):
    """CLI tool to add libraries to Compiler Explorer"""
    if debug:
        logging.basicConfig(level=logging.DEBUG, format="[%(levelname)s] %(name)s: %(message)s")

    click.echo("Welcome to CE Library Wizard!")
    click.echo("This tool will help you add a new library to Compiler Explorer.\n")

    try:
        # Try to get GitHub token if not provided
        if not github_token:
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

        # Handle top rust crates flag
        if top_rust_crates:
            process_top_rust_crates(github_token, verify, debug, keep_temp)
            return

        # If all parameters provided, skip interactive questions
        if lang and lib and ver:
            # Map language strings to enum values
            lang_map = {
                "c": Language.C,
                "c++": Language.CPP,
                "rust": Language.RUST,
                "fortran": Language.FORTRAN,
            }

            language = lang_map[lang.lower()]

            if language == Language.RUST:
                config = LibraryConfig(language=language, name=lib, version=ver)
            else:
                # For non-Rust, lib should be a GitHub URL
                config = LibraryConfig(language=language, github_url=lib, version=ver)

                # For C, C++, and Fortran, we need to set library_id
                if language == Language.C:
                    config.library_id = CHandler.suggest_library_id_static(lib)
                elif language == Language.CPP:
                    config.library_id = CppHandler.suggest_library_id_static(lib)
                elif language == Language.FORTRAN:
                    config.library_id = FortranHandler.suggest_library_id_static(lib)

                # Set library type if provided
                if type:
                    type_map = {
                        "header-only": LibraryType.HEADER_ONLY,
                        "packaged-headers": LibraryType.PACKAGED_HEADERS,
                        "static": LibraryType.STATIC,
                        "shared": LibraryType.SHARED,
                        "cshared": LibraryType.CSHARED,
                    }
                    config.library_type = type_map[type.lower()]
                    click.echo(f"✓ Using specified library type: {config.library_type.value}")

                # Normalize versions by checking git tags
                click.echo("Checking git tags for version format...")
                config.normalize_versions_with_git_lookup()
                if config.target_prefix:
                    click.echo(
                        f"✓ Detected version format requires target_prefix: {config.target_prefix}"
                    )
        else:
            # Interactive mode
            config = ask_library_questions()

        if debug:
            click.echo("\nLibrary Configuration:")
            click.echo(config.model_dump_json(indent=2))

        # Handle multi-version processing
        if config.is_multi_version():
            versions = config.get_versions()
            click.echo(f"\n🔢 Processing {len(versions)} versions: {', '.join(versions)}")

            for i, version in enumerate(versions, 1):
                click.echo(f"\n--- Processing version {i}/{len(versions)}: {version} ---")
                single_config = create_single_version_config(config, version)

                # Process each version individually
                if config.is_rust():
                    process_rust_library(single_config, github_token, verify, debug, keep_temp)
                elif config.language == Language.C:
                    process_c_library(
                        single_config, github_token, verify, debug, install_test, keep_temp
                    )
                elif config.language == Language.CPP:
                    process_cpp_library(
                        single_config, github_token, verify, debug, install_test, keep_temp
                    )
                elif config.language == Language.FORTRAN:
                    process_fortran_library(single_config, github_token, verify, debug, keep_temp)
                else:
                    click.echo(f"\n⚠️  Language {config.language} is not yet implemented.")
                    break
        else:
            # Single version processing (existing logic)
            if config.is_rust():
                process_rust_library(config, github_token, verify, debug, keep_temp)
            elif config.language == Language.C:
                process_c_library(config, github_token, verify, debug, install_test, keep_temp)
            elif config.language == Language.CPP:
                process_cpp_library(config, github_token, verify, debug, install_test, keep_temp)
            elif config.language == Language.FORTRAN:
                process_fortran_library(config, github_token, verify, debug, keep_temp)
            else:
                click.echo("\n⚠️  This language is not yet implemented.")
                click.echo(
                    "Currently only Rust, C, C++, and Fortran library additions are supported."
                )

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

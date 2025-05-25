#!/usr/bin/env python3
import click
import os
from pathlib import Path
from cli.questions import ask_library_questions
from core.models import LibraryConfig
from core.git_operations import GitManager
from core.rust_handler import RustLibraryHandler
from core.file_modifications import modify_main_repo_files, modify_infra_repo_files


def process_rust_library(config: LibraryConfig, github_token: str = None):
    """Process a Rust library addition"""
    click.echo(f"\nProcessing Rust crate: {config.name} v{config.version}")
    
    with GitManager(github_token) as git_mgr:
        click.echo("Cloning repositories...")
        main_repo_path, infra_repo_path = git_mgr.clone_repositories()
        
        # Create feature branches
        branch_name = f"add-rust-{config.name}-{config.version}".replace(".", "-")
        git_mgr.create_branch(git_mgr.infra_repo, f"infra/{branch_name}")
        git_mgr.create_branch(git_mgr.main_repo, f"main/{branch_name}")
        
        # Handle Rust-specific operations
        click.echo("Running ce_install to add crate...")
        rust_handler = RustLibraryHandler(infra_repo_path)
        
        try:
            libraries_yaml_path, new_props_content = rust_handler.process_rust_library(config)
            click.echo(f"✓ Modified {libraries_yaml_path.name}")
            
            # Update main repo with new properties
            click.echo("Updating rust.amazon.properties...")
            props_file = modify_main_repo_files(main_repo_path, config, new_props_content)
            click.echo(f"✓ Modified {props_file.name}")
            
            # Commit changes
            commit_msg = f"Add Rust crate {config.name} v{config.version}"
            
            git_mgr.commit_changes(git_mgr.infra_repo, commit_msg)
            git_mgr.commit_changes(git_mgr.main_repo, commit_msg)
            
            if github_token:
                # Push branches and create PRs
                click.echo("\nPushing branches...")
                git_mgr.push_branch(git_mgr.infra_repo, f"infra/{branch_name}")
                git_mgr.push_branch(git_mgr.main_repo, f"main/{branch_name}")
                
                click.echo("\nCreating pull requests...")
                pr_body = f"This PR adds the Rust crate **{config.name}** version {config.version} to Compiler Explorer."
                
                infra_pr_url = git_mgr.create_pull_request(
                    GitManager.CE_INFRA_REPO,
                    f"infra/{branch_name}",
                    commit_msg,
                    pr_body
                )
                
                main_pr_url = git_mgr.create_pull_request(
                    GitManager.CE_MAIN_REPO,
                    f"main/{branch_name}",
                    commit_msg,
                    pr_body + f"\n\nRelated PR: {infra_pr_url}"
                )
                
                click.echo(f"\n✓ Created PRs:")
                click.echo(f"  - Infra: {infra_pr_url}")
                click.echo(f"  - Main: {main_pr_url}")
            else:
                click.echo("\n⚠️  No GitHub token provided. Changes committed locally but not pushed.")
                click.echo("To push changes and create PRs, set GITHUB_TOKEN environment variable.")
                
        except Exception as e:
            click.echo(f"\n❌ Error processing Rust library: {e}", err=True)
            raise


@click.command()
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--github-token', envvar='GITHUB_TOKEN', help='GitHub token for creating PRs')
def main(debug: bool, github_token: str):
    """CLI tool to add libraries to Compiler Explorer"""
    click.echo("Welcome to CE Library Wizard!")
    click.echo("This tool will help you add a new library to Compiler Explorer.\n")
    
    try:
        config = ask_library_questions()
        
        if debug:
            click.echo("\nLibrary Configuration:")
            click.echo(config.model_dump_json(indent=2))
        
        if config.is_rust():
            process_rust_library(config, github_token)
        else:
            click.echo("\n⚠️  Non-Rust languages not yet implemented.")
            click.echo("Currently only Rust crate additions are supported.")
        
    except KeyboardInterrupt:
        click.echo("\n\nCancelled by user.")
        return 1
    except Exception as e:
        if debug:
            import traceback
            traceback.print_exc()
        click.echo(f"\nError: {e}", err=True)
        return 1


if __name__ == '__main__':
    main()
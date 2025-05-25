from pathlib import Path
from typing import Dict, Any, Optional
import re
from core.models import LibraryConfig


def generate_library_entry(config: LibraryConfig) -> Dict[str, Any]:
    """Generate the library configuration entry for compiler-explorer"""
    if config.is_rust():
        # Rust libraries are handled differently
        return {
            "name": config.name,
            "version": config.version
        }
    
    entry = {
        "id": config.github_url.split("/")[-1].lower(),
        "name": config.github_url.split("/")[-1],
        "version": config.version,
        "url": str(config.github_url),
    }
    
    if config.is_c_or_cpp():
        if config.is_header_only:
            entry["type"] = "header-only"
        else:
            entry["type"] = "compiled"
            entry["buildTool"] = config.build_tool.value
            entry["linkType"] = config.link_type.value
            entry["binaries"] = config.binary_names
    
    return entry


def update_rust_properties(repo_path: Path, new_props_content: str):
    """Update the Rust properties file with new library information"""
    rust_props_path = repo_path / "etc" / "config" / "rust.amazon.properties"
    
    if not rust_props_path.exists():
        raise FileNotFoundError(f"Rust properties file not found at {rust_props_path}")
    
    # Read the existing file
    current_content = rust_props_path.read_text()
    
    # Find the libs= line and everything after it
    libs_pattern = re.compile(r'^libs=.*$', re.MULTILINE | re.DOTALL)
    match = libs_pattern.search(current_content)
    
    if not match:
        raise ValueError("Could not find 'libs=' line in rust.amazon.properties")
    
    # Replace from libs= to the end of file with new content
    libs_start = match.start()
    new_content = current_content[:libs_start] + new_props_content
    
    # Write the updated content
    rust_props_path.write_text(new_content)
    
    return rust_props_path


def modify_main_repo_files(repo_path: Path, config: LibraryConfig, 
                          rust_props_content: Optional[str] = None):
    """Modify files in the main compiler-explorer repository"""
    if config.is_rust() and rust_props_content:
        # For Rust, we only need to update the properties file
        return update_rust_properties(repo_path, rust_props_content)
    
    # TODO: Implement for other languages
    # This will involve:
    # 1. Finding the appropriate library configuration file for the language
    # 2. Adding the new library entry
    # 3. Ensuring proper formatting and validation
    pass


def modify_infra_repo_files(repo_path: Path, config: LibraryConfig):
    """Modify files in the infra repository"""
    if config.is_rust():
        # Rust modifications are handled by ce_install in rust_handler.py
        # The libraries.yaml file is already modified by add-crate command
        return
    
    # TODO: Implement for other languages
    # This will involve:
    # 1. Finding the appropriate build/deployment configuration
    # 2. Adding necessary build steps or configurations
    # 3. Ensuring the library can be properly built and deployed
    pass
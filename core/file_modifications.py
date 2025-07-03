from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.models import LibraryConfig


def generate_library_entry(config: LibraryConfig) -> dict[str, Any]:
    """Generate the library configuration entry for compiler-explorer"""
    if config.is_rust():
        # Rust libraries are handled differently
        return {"name": config.name, "version": config.version}

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

    # Find the libs= section
    libs_match = re.search(r"^libs=", current_content, re.MULTILINE)
    if not libs_match:
        raise ValueError("Could not find 'libs=' line in rust.amazon.properties")

    libs_start = libs_match.start()

    # Find the end of the libs section
    # Look for the delimiter or the start of tools section
    delimiter_pattern = re.compile(r"^#################################", re.MULTILINE)
    tools_pattern = re.compile(r"^tools=", re.MULTILINE)

    # Search for delimiter after libs=
    delimiter_match = delimiter_pattern.search(current_content, libs_start)
    tools_match = tools_pattern.search(current_content, libs_start)

    # Determine the end of libs section
    libs_end = len(current_content)  # Default to end of file

    if delimiter_match and tools_match:
        # Use whichever comes first
        libs_end = min(delimiter_match.start(), tools_match.start())
    elif delimiter_match:
        libs_end = delimiter_match.start()
    elif tools_match:
        libs_end = tools_match.start()

    # Build the new content
    # Ensure new_props_content ends with a newline to avoid end-of-file issues
    if not new_props_content.endswith("\n"):
        new_props_content += "\n"

    new_content = (
        current_content[:libs_start]
        + new_props_content  # Everything before libs=
        + current_content[libs_end:]  # New libs content  # Everything after libs section
    )

    # Write the updated content
    rust_props_path.write_text(new_content)

    return rust_props_path

"""Build testing utilities for libraries that require compilation."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .subprocess_utils import run_ce_install_command

logger = logging.getLogger(__name__)


@dataclass
class InstalledCompiler:
    """Represents an installed compiler."""

    name: str
    version: str
    compiler_id: str

    def __str__(self) -> str:
        return f"{self.name} {self.version} ({self.compiler_id})"


@dataclass
class BuildTestResult:
    """Result of a build test including artifact information."""

    success: bool
    message: str
    compiler_id: str | None = None
    staging_dir: str | None = None
    install_dir: str | None = None
    artifacts: list[str] = field(default_factory=list)
    link_verification: dict[str, bool] = field(default_factory=dict)
    missing_links: list[str] = field(default_factory=list)

    def get_artifact_summary(self) -> str:
        """Get a human-readable summary of artifacts."""
        if not self.artifacts:
            return "No artifacts found"

        # Categorize artifacts
        libs = [
            a for a in self.artifacts if a.endswith((".a", ".so", ".so.*", ".rlib")) or ".so." in a
        ]
        rust_meta = [a for a in self.artifacts if a.endswith(".rmeta")]
        headers = [a for a in self.artifacts if a.endswith((".h", ".hpp", ".hxx", ".hh"))]
        fortran_src = [
            a for a in self.artifacts if a.endswith((".f90", ".F90", ".f", ".F", ".f95", ".F95"))
        ]
        fortran_mod = [a for a in self.artifacts if a.endswith(".mod")]
        categorized = set(libs + rust_meta + headers + fortran_src + fortran_mod)
        others = [a for a in self.artifacts if a not in categorized]

        parts = []
        if libs:
            parts.append(f"Libraries: {', '.join(Path(lib).name for lib in libs)}")
        if rust_meta:
            parts.append(f"Rust metadata: {', '.join(Path(m).name for m in rust_meta)}")
        if headers:
            parts.append(f"Headers: {', '.join(Path(h).name for h in headers)}")
        if fortran_mod:
            parts.append(f"Fortran modules: {', '.join(Path(m).name for m in fortran_mod)}")
        if fortran_src:
            src_names = [Path(s).name for s in fortran_src[:5]]
            if len(fortran_src) > 5:
                src_names.append(f"... and {len(fortran_src) - 5} more")
            parts.append(f"Fortran sources: {', '.join(src_names)}")
        if others:
            other_names = [Path(o).name for o in others[:5]]
            if len(others) > 5:
                other_names.append(f"... and {len(others) - 5} more")
            parts.append(f"Other: {', '.join(other_names)}")

        return "\n  ".join(parts) if parts else "No artifacts found"

    def get_link_verification_summary(self) -> str:
        """Get a summary of link library verification."""
        if not self.link_verification:
            return "No link libraries configured"

        lines = []
        for link_name, found in self.link_verification.items():
            status = "✓" if found else "✗ MISSING"
            lines.append(f"{status} -l{link_name}")

        return "\n  ".join(lines)

    def get_linkable_libraries(self) -> list[str]:
        """Extract link names from artifacts (e.g., 'z' from 'libz.a')."""
        link_names = set()
        for artifact in self.artifacts:
            name = Path(artifact).name
            # Match libXXX.a or libXXX.so
            if name.startswith("lib") and (name.endswith(".a") or ".so" in name):
                # Extract the link name (remove 'lib' prefix and extension)
                base = name[3:]  # Remove 'lib'
                if base.endswith(".a"):
                    link_names.add(base[:-2])
                elif ".so" in base:
                    # Handle libz.so, libz.so.1, libz.so.1.3.1
                    link_names.add(base.split(".so")[0])
        return sorted(link_names)


def parse_semver(version: str) -> tuple[int, int, int]:
    """
    Parse a semantic version string into a tuple for comparison.

    Args:
        version: Version string (e.g., "14.2.0", "14.2", "14")

    Returns:
        Tuple of (major, minor, patch) integers
    """
    # Remove common prefixes
    version = version.lstrip("v")

    # Split and parse
    parts = version.split(".")
    major = int(parts[0]) if len(parts) > 0 and parts[0].isdigit() else 0
    minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    patch = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0

    return (major, minor, patch)


def detect_installed_compilers(
    infra_path: Path,
    compiler_family: str = "gcc",
    debug: bool = False,
) -> list[InstalledCompiler]:
    """
    Detect installed compilers using ce_install.

    Args:
        infra_path: Path to the infra repository
        compiler_family: Compiler family to search for (e.g., "gcc", "clang")
        debug: Enable debug logging

    Returns:
        List of installed compilers sorted by version (newest first)
    """
    try:
        # Run ce_install list command to get installed compilers
        # Command: bin/ce_install --filter-match-all list --installed-only
        #          --show-compiler-ids --json gcc '!cross'
        subcommand = [
            "--filter-match-all",
            "list",
            "--installed-only",
            "--show-compiler-ids",
            "--json",
            compiler_family,
            "!cross",
        ]

        logger.info(f"Detecting installed {compiler_family} compilers...")
        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        if result.returncode != 0:
            logger.error(f"Failed to list installed compilers: {result.stderr}")
            return []

        # Parse JSON output
        output = result.stdout.strip()
        if not output:
            logger.warning("No output from ce_install list command")
            return []

        try:
            compilers_data = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse compiler list JSON: {e}")
            if debug:
                logger.debug(f"Raw output: {output}")
            return []

        # Parse compiler entries
        # Format from ce_install: list of objects with target_name (version) and compiler_ids
        compilers = []
        for entry in compilers_data:
            if isinstance(entry, dict):
                # ce_install format: {"target_name": "14.2.0", "compiler_ids": ["g142", ...], ...}
                version = entry.get("target_name", "")
                compiler_ids = entry.get("compiler_ids", [])
                name = entry.get("name", compiler_family)

                # Skip non-version entries (like "renovated-3.4.6")
                if not version or not compiler_ids:
                    continue

                # Check if version looks like a semver (starts with digit)
                if not version[0].isdigit():
                    continue

                # Use the first compiler_id (primary one, without objcpp prefix)
                compiler_id = compiler_ids[0] if compiler_ids else ""

                if version and compiler_id:
                    compilers.append(
                        InstalledCompiler(name=name, version=version, compiler_id=compiler_id)
                    )
            elif isinstance(entry, str):
                # Try to parse string format: "gcc 14.2.0 (g142)"
                match = re.match(r"(\w+)\s+([\d.]+)\s+\((\w+)\)", entry)
                if match:
                    compilers.append(
                        InstalledCompiler(
                            name=match.group(1),
                            version=match.group(2),
                            compiler_id=match.group(3),
                        )
                    )

        # Sort by version (newest first)
        compilers.sort(key=lambda c: parse_semver(c.version), reverse=True)

        if compilers:
            logger.info(f"Found {len(compilers)} installed {compiler_family} compiler(s)")
            if debug:
                for c in compilers[:5]:
                    logger.debug(f"  - {c}")
        else:
            logger.warning(f"No installed {compiler_family} compilers found")

        return compilers

    except Exception as e:
        logger.error(f"Error detecting installed compilers: {e}")
        return []


def get_latest_compiler(
    infra_path: Path,
    compiler_family: str = "gcc",
    debug: bool = False,
) -> InstalledCompiler | None:
    """
    Get the latest installed compiler for a given family.

    Args:
        infra_path: Path to the infra repository
        compiler_family: Compiler family to search for
        debug: Enable debug logging

    Returns:
        The latest installed compiler, or None if none found
    """
    compilers = detect_installed_compilers(infra_path, compiler_family, debug)
    return compilers[0] if compilers else None


def _find_staging_dirs(output: str) -> list[str]:
    """Extract staging directory paths from build output."""
    # Pattern: /tmp/ce-cefs-temp/staging/<uuid>
    pattern = r"/tmp/ce-cefs-temp/staging/[a-f0-9-]+"
    matches = re.findall(pattern, output)
    # Return unique paths
    return list(set(matches))


def _list_artifacts(install_dir: Path) -> list[str]:
    """List artifact files in the install directory."""
    if not install_dir.exists():
        return []

    artifacts = []
    for f in install_dir.rglob("*"):
        if f.is_file():
            # Get path relative to install dir
            artifacts.append(str(f.relative_to(install_dir)))
    return sorted(artifacts)


def _get_expected_link_libraries(
    infra_path: Path, library_id: str, language: str
) -> tuple[list[str], list[str]]:
    """
    Read expected link libraries from libraries.yaml.

    Args:
        infra_path: Path to the infra repository
        library_id: The library identifier
        language: Library language ("c" or "c++")

    Returns:
        Tuple of (static_links, shared_links) - lists of expected link library names
    """
    libraries_yaml = infra_path / "bin" / "yaml" / "libraries.yaml"
    if not libraries_yaml.exists():
        logger.warning(f"libraries.yaml not found at {libraries_yaml}")
        return [], []

    try:
        with open(libraries_yaml) as f:
            data = yaml.safe_load(f)

        # Navigate to the library section (structure: libraries -> language -> library)
        if "libraries" not in data:
            logger.warning("'libraries' key not found in libraries.yaml")
            return [], []

        libraries = data["libraries"]
        lang_key = "c++" if language == "c++" else language
        if lang_key not in libraries:
            logger.warning(f"Language '{lang_key}' not found in libraries.yaml")
            return [], []

        lang_libs = libraries[lang_key]
        if library_id not in lang_libs:
            logger.warning(f"Library '{library_id}' not found in libraries.yaml")
            return [], []

        lib_config = lang_libs[library_id]
        static_links = lib_config.get("staticliblink", [])
        shared_links = lib_config.get("sharedliblink", [])

        # Ensure they're lists
        if isinstance(static_links, str):
            static_links = [static_links]
        if isinstance(shared_links, str):
            shared_links = [shared_links]

        return static_links, shared_links

    except Exception as e:
        logger.warning(f"Error reading libraries.yaml: {e}")
        return [], []


def _verify_link_libraries(
    artifacts: list[str], static_links: list[str], shared_links: list[str]
) -> tuple[dict[str, bool], list[str]]:
    """
    Verify that expected link libraries exist in artifacts.

    Args:
        artifacts: List of artifact paths
        static_links: Expected static link library names
        shared_links: Expected shared link library names

    Returns:
        Tuple of (verification_dict, missing_links)
    """
    # Extract library names from artifacts
    artifact_libs = set()
    for artifact in artifacts:
        name = Path(artifact).name
        if name.startswith("lib"):
            if name.endswith(".a"):
                # Static lib: libz.a -> z
                artifact_libs.add(("static", name[3:-2]))
            elif ".so" in name:
                # Shared lib: libz.so -> z
                base = name[3:].split(".so")[0]
                artifact_libs.add(("shared", base))

    verification = {}
    missing = []

    # Check static libraries
    for link in static_links:
        found = ("static", link) in artifact_libs
        verification[f"{link} (static)"] = found
        if not found:
            missing.append(f"lib{link}.a")

    # Check shared libraries
    for link in shared_links:
        found = ("shared", link) in artifact_libs
        verification[f"{link} (shared)"] = found
        if not found:
            missing.append(f"lib{link}.so")

    return verification, missing


def run_build_test(
    infra_path: Path,
    library_id: str,
    version: str,
    language: str = "c++",
    compiler_id: str | None = None,
    compiler_family: str = "gcc",
    debug: bool = False,
) -> BuildTestResult:
    """
    Test building a library using ce_install build command.

    Args:
        infra_path: Path to the infra repository
        library_id: The library identifier
        version: The library version
        language: Library language ("c" or "c++")
        compiler_id: Specific compiler ID to use (auto-detected if None)
        compiler_family: Compiler family to use if auto-detecting
        debug: Enable debug logging

    Returns:
        BuildTestResult with success status, message, and artifact information
    """
    try:
        # Get compiler ID if not specified
        if not compiler_id:
            compiler = get_latest_compiler(infra_path, compiler_family, debug)
            if not compiler:
                return BuildTestResult(
                    success=False,
                    message=(
                        f"No installed {compiler_family} compilers found. "
                        f"Install a compiler using ce_install first."
                    ),
                )
            compiler_id = compiler.compiler_id
            logger.info(f"Using compiler: {compiler}")

        # Construct the library spec
        library_spec = f"libraries/{language}/{library_id} {version}"

        # Build the command
        # Command: bin/ce_install --debug --dry-run --keep-staging build
        #          --temp-install --buildfor <compiler_id> '<library_spec>'
        subcommand = [
            "--debug",
            "--dry-run",
            "--keep-staging",
            "build",
            "--temp-install",
            "--buildfor",
            compiler_id,
            library_spec,
        ]

        logger.info(f"Running build test for {library_id} {version} with {compiler_id}...")
        logger.info(f"Command: bin/ce_install {' '.join(subcommand)}")

        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        output = f"{result.stdout}\n{result.stderr}".strip()

        if result.returncode != 0:
            logger.error(f"Build test failed with exit code {result.returncode}")
            if debug:
                logger.debug(f"Output: {output}")
            return BuildTestResult(
                success=False,
                message=f"Build test failed: {output}",
                compiler_id=compiler_id,
            )

        # Parse staging directories from output
        staging_dirs = _find_staging_dirs(output)
        staging_dir = staging_dirs[0] if staging_dirs else None
        install_dir = None
        artifacts: list[str] = []

        if staging_dir:
            # Check for install directory
            install_path = Path(staging_dir) / "install"
            if install_path.exists():
                install_dir = str(install_path)
                artifacts = _list_artifacts(install_path)
                logger.info(f"Found {len(artifacts)} artifacts in {install_dir}")

        # Verify link libraries
        static_links, shared_links = _get_expected_link_libraries(infra_path, library_id, language)
        link_verification: dict[str, bool] = {}
        missing_links: list[str] = []

        if static_links or shared_links:
            link_verification, missing_links = _verify_link_libraries(
                artifacts, static_links, shared_links
            )
            if missing_links:
                logger.warning(f"Missing expected link libraries: {missing_links}")
            else:
                logger.info("All expected link libraries verified")

        logger.info("Build test completed successfully")
        return BuildTestResult(
            success=True,
            message=f"Build test passed using compiler {compiler_id}",
            compiler_id=compiler_id,
            staging_dir=staging_dir,
            install_dir=install_dir,
            artifacts=artifacts,
            link_verification=link_verification,
            missing_links=missing_links,
        )

    except Exception as e:
        logger.error(f"Error during build test: {e}")
        return BuildTestResult(
            success=False,
            message=f"Build test error: {e}",
        )


def check_build_test_available(infra_path: Path, debug: bool = False) -> tuple[bool, str]:
    """
    Check if build testing is available (compiler installed).

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        Tuple of (available, message)
    """
    # Check for GCC first (most common)
    gcc_compiler = get_latest_compiler(infra_path, "gcc", debug)
    if gcc_compiler:
        return (True, f"Build testing available with {gcc_compiler}")

    # Check for Clang as fallback
    clang_compiler = get_latest_compiler(infra_path, "clang", debug)
    if clang_compiler:
        return (True, f"Build testing available with {clang_compiler}")

    return (
        False,
        "No compilers installed. Install a compiler using ce_install to enable build testing.",
    )


# Rust-specific build testing functions


def detect_installed_rust_compilers(
    infra_path: Path,
    debug: bool = False,
) -> list[InstalledCompiler]:
    """
    Detect installed Rust compilers using ce_install.

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        List of installed Rust compilers sorted by version (newest first)
    """
    try:
        # Run ce_install list command to get installed Rust compilers
        # Filter for "rust" and exclude nightly/beta for stability
        subcommand = [
            "--filter-match-all",
            "list",
            "--installed-only",
            "--show-compiler-ids",
            "--json",
            "rust",
            "!nightly",
            "!beta",
        ]

        logger.info("Detecting installed Rust compilers...")
        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        if result.returncode != 0:
            logger.error(f"Failed to list installed Rust compilers: {result.stderr}")
            return []

        output = result.stdout.strip()
        if not output:
            logger.warning("No output from ce_install list command")
            return []

        try:
            compilers_data = json.loads(output)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse compiler list JSON: {e}")
            return []

        compilers = []
        for entry in compilers_data:
            if isinstance(entry, dict):
                # Skip libraries, only want compilers
                if entry.get("is_library", False):
                    continue

                version = entry.get("target_name", "")
                compiler_ids = entry.get("compiler_ids", [])
                name = entry.get("name", "rust")

                if not version or not compiler_ids:
                    continue

                # Check if version looks like a semver
                if not version[0].isdigit():
                    continue

                compiler_id = compiler_ids[0] if compiler_ids else ""

                if version and compiler_id:
                    compilers.append(
                        InstalledCompiler(name=name, version=version, compiler_id=compiler_id)
                    )

        # Sort by version (newest first)
        compilers.sort(key=lambda c: parse_semver(c.version), reverse=True)

        if compilers:
            logger.info(f"Found {len(compilers)} installed Rust compiler(s)")
            if debug:
                for c in compilers[:5]:
                    logger.debug(f"  - {c}")
        else:
            logger.warning("No installed Rust compilers found")

        return compilers

    except Exception as e:
        logger.error(f"Error detecting installed Rust compilers: {e}")
        return []


def get_latest_rust_compiler(
    infra_path: Path,
    debug: bool = False,
) -> InstalledCompiler | None:
    """
    Get the latest installed Rust compiler.

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        The latest installed Rust compiler, or None if none found
    """
    compilers = detect_installed_rust_compilers(infra_path, debug)
    return compilers[0] if compilers else None


def _find_rust_artifacts(staging_dirs: list[str], compiler_id: str) -> tuple[str | None, list[str]]:
    """
    Find Rust build artifacts in staging directories.

    Rust builds have a different structure:
    - staging/<uuid>/<compiler_id>_<hash>/build/debug/lib<crate>.rlib
    - staging/<uuid>/crate_<name>_<version>/ (source files)

    Args:
        staging_dirs: List of staging directory paths
        compiler_id: The Rust compiler ID used for the build

    Returns:
        Tuple of (build_dir, artifacts) where artifacts are relative paths
    """
    for staging_dir in staging_dirs:
        staging_path = Path(staging_dir)
        if not staging_path.exists():
            continue

        # Look for compiler-specific build directory
        for subdir in staging_path.iterdir():
            if subdir.is_dir() and subdir.name.startswith(f"{compiler_id}_"):
                # This is the build directory
                build_debug = subdir / "build" / "debug"
                if build_debug.exists():
                    artifacts = []
                    for f in build_debug.rglob("*"):
                        if f.is_file() and (
                            f.suffix in (".rlib", ".rmeta", ".d") or f.name.endswith(".rlib")
                        ):
                            artifacts.append(str(f.relative_to(build_debug)))
                    return str(build_debug), sorted(artifacts)

    return None, []


def run_rust_build_test(
    infra_path: Path,
    crate_name: str,
    version: str,
    compiler_id: str | None = None,
    debug: bool = False,
) -> BuildTestResult:
    """
    Test building a Rust crate using ce_install build command.

    Args:
        infra_path: Path to the infra repository
        crate_name: The crate name
        version: The crate version
        compiler_id: Specific Rust compiler ID to use (auto-detected if None)
        debug: Enable debug logging

    Returns:
        BuildTestResult with success status, message, and artifact information
    """
    try:
        # Get compiler ID if not specified
        if not compiler_id:
            compiler = get_latest_rust_compiler(infra_path, debug)
            if not compiler:
                return BuildTestResult(
                    success=False,
                    message=(
                        "No installed Rust compilers found. "
                        "Install a Rust compiler using ce_install first."
                    ),
                )
            compiler_id = compiler.compiler_id
            logger.info(f"Using Rust compiler: {compiler}")

        # Construct the library spec
        library_spec = f"libraries/rust/{crate_name} {version}"

        # Build the command
        subcommand = [
            "--debug",
            "--dry-run",
            "--keep-staging",
            "build",
            "--temp-install",
            "--buildfor",
            compiler_id,
            library_spec,
        ]

        logger.info(f"Running Rust build test for {crate_name} {version} with {compiler_id}...")
        logger.info(f"Command: bin/ce_install {' '.join(subcommand)}")

        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        output = f"{result.stdout}\n{result.stderr}".strip()

        if result.returncode != 0:
            logger.error(f"Rust build test failed with exit code {result.returncode}")
            if debug:
                logger.debug(f"Output: {output}")
            return BuildTestResult(
                success=False,
                message=f"Rust build test failed: {output}",
                compiler_id=compiler_id,
            )

        # Parse staging directories from output
        staging_dirs = _find_staging_dirs(output)
        build_dir, artifacts = _find_rust_artifacts(staging_dirs, compiler_id)

        # Check for .rlib files specifically
        rlib_count = sum(1 for a in artifacts if a.endswith(".rlib"))

        if rlib_count == 0:
            logger.warning("No .rlib files found in build output")

        logger.info(f"Rust build test completed successfully with {rlib_count} .rlib file(s)")
        return BuildTestResult(
            success=True,
            message=f"Rust build test passed using compiler {compiler_id}",
            compiler_id=compiler_id,
            staging_dir=staging_dirs[0] if staging_dirs else None,
            install_dir=build_dir,
            artifacts=artifacts,
        )

    except Exception as e:
        logger.error(f"Error during Rust build test: {e}")
        return BuildTestResult(
            success=False,
            message=f"Rust build test error: {e}",
        )


def check_rust_build_test_available(infra_path: Path, debug: bool = False) -> tuple[bool, str]:
    """
    Check if Rust build testing is available (Rust compiler installed).

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        Tuple of (available, message)
    """
    rust_compiler = get_latest_rust_compiler(infra_path, debug)
    if rust_compiler:
        return (True, f"Rust build testing available with {rust_compiler}")

    return (
        False,
        "No Rust compilers installed. Install a Rust compiler using ce_install first.",
    )


# Fortran-specific build testing functions


def detect_installed_fortran_compilers(
    infra_path: Path,
    debug: bool = False,
) -> list[InstalledCompiler]:
    """
    Detect installed Fortran compilers using ce_install.

    This function checks both dedicated Fortran compilers (Intel, LFortran) and
    gcc compilers that include gfortran.

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        List of installed Fortran compilers sorted by version (newest first)
    """
    compilers: list[InstalledCompiler] = []

    # First, check for gcc compilers that include gfortran
    # gfortran comes bundled with gcc and can be used for Fortran library builds
    try:
        gcc_compilers = detect_installed_compilers(infra_path, "gcc", debug)
        for gcc in gcc_compilers:
            # Check if this gcc installation has gfortran
            # gcc installations are typically at /opt/compiler-explorer/gcc-<version>
            gcc_path = Path("/opt/compiler-explorer") / f"gcc-{gcc.version}"
            gfortran_bin = gcc_path / "bin" / "gfortran"

            if gfortran_bin.exists():
                compilers.append(
                    InstalledCompiler(
                        name=f"gfortran (gcc {gcc.version})",
                        version=gcc.version,
                        compiler_id=gcc.compiler_id,
                    )
                )
                if debug:
                    logger.debug(f"Found gfortran in gcc {gcc.version} at {gfortran_bin}")
    except Exception as e:
        logger.warning(f"Error checking for gfortran in gcc: {e}")

    # Also check for dedicated Fortran compilers (Intel, LFortran)
    try:
        subcommand = [
            "--filter-match-all",
            "list",
            "--installed-only",
            "--show-compiler-ids",
            "--json",
            "fortran",
        ]

        logger.info("Detecting installed Fortran compilers...")
        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        if result.returncode == 0:
            output = result.stdout.strip()
            if output:
                try:
                    compilers_data = json.loads(output)
                    for entry in compilers_data:
                        if isinstance(entry, dict):
                            if entry.get("is_library", False):
                                continue

                            version = entry.get("target_name", "")
                            compiler_ids = entry.get("compiler_ids", [])
                            name = entry.get("name", "fortran")

                            if not version or not compiler_ids:
                                continue

                            compiler_id = compiler_ids[0] if compiler_ids else ""

                            if version and compiler_id:
                                compilers.append(
                                    InstalledCompiler(
                                        name=name, version=version, compiler_id=compiler_id
                                    )
                                )
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse compiler list JSON: {e}")
    except Exception as e:
        logger.error(f"Error detecting dedicated Fortran compilers: {e}")

    if compilers:
        logger.info(f"Found {len(compilers)} installed Fortran compiler(s)")
        if debug:
            for c in compilers[:5]:
                logger.debug(f"  - {c}")
    else:
        logger.warning("No installed Fortran compilers found")

    return compilers


def get_latest_fortran_compiler(
    infra_path: Path,
    debug: bool = False,
) -> InstalledCompiler | None:
    """
    Get the latest installed Fortran compiler, preferring gfortran over Intel Fortran.

    Priority order:
    1. gfortran (from gcc) - most compatible and widely used
    2. LFortran - modern Fortran compiler
    3. Intel Fortran - proprietary, may have compatibility issues

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        The latest installed Fortran compiler, or None if none found
    """
    compilers = detect_installed_fortran_compilers(infra_path, debug)
    if not compilers:
        return None

    # Prefer gfortran (usually from gcc installations)
    gfortran_compilers = [c for c in compilers if "gfortran" in c.name.lower()]
    if gfortran_compilers:
        # Sort by version and return the latest
        gfortran_compilers.sort(key=lambda c: parse_semver(c.version), reverse=True)
        return gfortran_compilers[0]

    # Next, prefer LFortran
    lfortran_compilers = [c for c in compilers if "lfortran" in c.name.lower()]
    if lfortran_compilers:
        lfortran_compilers.sort(key=lambda c: parse_semver(c.version), reverse=True)
        return lfortran_compilers[0]

    # Fall back to any available Fortran compiler (e.g., Intel)
    return compilers[0]


def run_fortran_build_test(
    infra_path: Path,
    library_id: str,
    version: str,
    compiler_id: str | None = None,
    debug: bool = False,
) -> BuildTestResult:
    """
    Test building a Fortran library using ce_install build command.

    Note: Fortran libraries using fpm (Fortran Package Manager) don't compile
    during the build step - they package source files. The actual compilation
    happens at runtime. This test verifies the build process completes successfully.

    Args:
        infra_path: Path to the infra repository
        library_id: The library identifier
        version: The library version
        compiler_id: Specific Fortran compiler ID to use (auto-detected if None)
        debug: Enable debug logging

    Returns:
        BuildTestResult with success status, message, and artifact information
    """
    try:
        # Get compiler ID if not specified
        if not compiler_id:
            compiler = get_latest_fortran_compiler(infra_path, debug)
            if not compiler:
                return BuildTestResult(
                    success=False,
                    message=(
                        "No installed Fortran compilers found. "
                        "Install a Fortran compiler using ce_install first."
                    ),
                )
            compiler_id = compiler.compiler_id
            logger.info(f"Using Fortran compiler: {compiler}")

        # Construct the library spec
        library_spec = f"libraries/fortran/{library_id} {version}"

        # Build the command - note: we can't use --dry-run for fpm libraries
        # as they need to be "installed" (source extracted) to verify
        subcommand = [
            "--debug",
            "--keep-staging",
            "build",
            "--temp-install",
            "--buildfor",
            compiler_id,
            library_spec,
        ]

        logger.info(f"Running Fortran build test for {library_id} {version}...")
        logger.info(f"Command: bin/ce_install {' '.join(subcommand)}")

        result = run_ce_install_command(subcommand, cwd=infra_path, debug=debug)

        output = f"{result.stdout}\n{result.stderr}".strip()

        # Check for success - fpm libraries may fail at deployment stage (permission error)
        # but that's OK for testing purposes - we just want to verify the source is valid
        if result.returncode != 0:
            # Check if it failed at deployment stage (permission error is expected)
            if "PermissionError" in output and "cefs-images" in output:
                logger.info("Build completed but deployment failed (expected in test mode)")
            else:
                logger.error(f"Fortran build test failed with exit code {result.returncode}")
                if debug:
                    logger.debug(f"Output: {output}")
                return BuildTestResult(
                    success=False,
                    message=f"Fortran build test failed: {output}",
                    compiler_id=compiler_id,
                )

        # Parse staging directories from output
        staging_dirs = _find_staging_dirs(output)
        staging_dir = staging_dirs[0] if staging_dirs else None
        artifacts: list[str] = []

        if staging_dir:
            # For fpm libraries, the artifacts are source files (.f90, .F90, fpm.toml)
            staging_path = Path(staging_dir)
            if staging_path.exists():
                for f in staging_path.rglob("*"):
                    if f.is_file():
                        rel_path = str(f.relative_to(staging_path))
                        # Include relevant Fortran files
                        if any(
                            rel_path.endswith(ext)
                            for ext in (".f90", ".F90", ".f", ".F", ".mod", ".o", ".a", ".toml")
                        ):
                            artifacts.append(rel_path)

                artifacts = sorted(artifacts)[:50]  # Limit to 50 artifacts
                logger.info(f"Found {len(artifacts)} source/build artifacts")

        logger.info("Fortran build test completed successfully")
        return BuildTestResult(
            success=True,
            message=f"Fortran build test passed using compiler {compiler_id}",
            compiler_id=compiler_id,
            staging_dir=staging_dir,
            artifacts=artifacts,
        )

    except Exception as e:
        logger.error(f"Error during Fortran build test: {e}")
        return BuildTestResult(
            success=False,
            message=f"Fortran build test error: {e}",
        )


def check_fortran_build_test_available(infra_path: Path, debug: bool = False) -> tuple[bool, str]:
    """
    Check if Fortran build testing is available (Fortran compiler installed).

    Args:
        infra_path: Path to the infra repository
        debug: Enable debug logging

    Returns:
        Tuple of (available, message)
    """
    fortran_compiler = get_latest_fortran_compiler(infra_path, debug)
    if fortran_compiler:
        return (True, f"Fortran build testing available with {fortran_compiler}")

    return (
        False,
        "No Fortran compilers installed. Install a Fortran compiler using ce_install first.",
    )

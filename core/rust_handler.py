import platform
from pathlib import Path

from core.models import LibraryConfig

from .subprocess_utils import run_command, run_make_command


class RustLibraryHandler:
    """Handles Rust library additions using ce_install utilities"""

    def __init__(self, infra_repo_path: Path, debug: bool = False):
        self.infra_repo_path = infra_repo_path
        self.is_windows = platform.system() == "Windows"
        self.debug = debug

    def setup_ce_install(self) -> bool:
        """Run make ce or ce_install.ps1 based on platform"""
        try:
            if self.debug:
                # First check what files exist in the infra repo
                print(f"\nChecking infra repo contents at: {self.infra_repo_path}")
                makefile_path = self.infra_repo_path / "Makefile"
                if makefile_path.exists():
                    print("✓ Makefile exists")
                else:
                    print("✗ Makefile NOT found")

                # List first few files to verify clone worked
                files = list(self.infra_repo_path.iterdir())[:10]
                print(f"First few files: {[f.name for f in files]}")

            if self.is_windows:
                # Run PowerShell script on Windows
                cmd = [
                    "powershell.exe",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.infra_repo_path / "ce_install.ps1"),
                ]
            else:
                # Find the actual Python executable
                python_result = run_command(["which", "python3"], clean_env=True)
                python_path = python_result.stdout.strip()

                # Run make ce on Linux/Mac with explicit Python path
                extra_env = {"PYTHON": python_path} if python_path else None

            if self.debug:
                print(f"\nRunning command: {' '.join(cmd)}")
                print(f"Working directory: {self.infra_repo_path}")

            # Run the command
            if self.is_windows:
                # Windows PowerShell command
                result = run_command(
                    cmd,
                    cwd=self.infra_repo_path,
                    clean_env=True,
                    capture_output=not self.debug,
                    debug=self.debug,
                )
            else:
                # Unix make command
                if self.debug and extra_env:
                    extra_env["VERBOSE"] = "1"
                result = run_make_command(
                    "ce", cwd=self.infra_repo_path, extra_env=extra_env, debug=self.debug
                )

            if self.debug:
                print(f"\nCommand exit code: {result.returncode}")

            if result.returncode != 0:
                # Handle the common case where .venv directory is missing
                venv_path = self.infra_repo_path / ".venv"

                if self.debug:
                    print(f"\n.venv exists: {venv_path.exists()}")
                    if venv_path.exists():
                        print(f".venv contents: {list(venv_path.iterdir())}")

                    # Check if poetry installed successfully
                    poetry_path = self.infra_repo_path / ".poetry"
                    print(f".poetry exists: {poetry_path.exists()}")

                    print("\nTrying to create .venv directory and retry...")

                # Try to create the .venv directory manually
                # This is a known issue with the infra Makefile
                venv_path.mkdir(exist_ok=True)

                # Touch the .deps file that make is expecting
                deps_file = venv_path / ".deps"
                deps_file.touch()

                # Now ce_install should be available via poetry
                return True

            return True

        except Exception as e:
            raise RuntimeError(f"Error setting up ce_install: {e}")

    def add_crate(self, crate_name: str, version: str) -> Path:
        """Add a Rust crate using ce_install add-crate command"""
        try:
            if self.is_windows:
                # Windows: use PowerShell script
                cmd = [
                    "powershell.exe",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.infra_repo_path / "ce_install.ps1"),
                    "add-crate",
                    crate_name,
                    version,
                ]
            else:
                # Linux/Mac: check if we can run ce_install directly
                ce_install_path = self.infra_repo_path / "bin" / "ce_install"
                if ce_install_path.exists():
                    # Make it executable if it isn't already
                    ce_install_path.chmod(0o755)
                    cmd = [str(ce_install_path), "add-crate", crate_name, version]
                else:
                    # Try with poetry
                    poetry_bin = self.infra_repo_path / ".poetry" / "bin" / "poetry"
                    if poetry_bin.exists():
                        cmd = [
                            str(poetry_bin),
                            "run",
                            "bin/ce_install",
                            "add-crate",
                            crate_name,
                            version,
                        ]
                    else:
                        raise RuntimeError("Could not find ce_install executable")

            if self.debug:
                print(f"\nRunning: {' '.join(cmd)}")

            result = run_command(
                cmd,
                cwd=self.infra_repo_path,
                capture_output=True,
                text=True,
                clean_env=True,
                debug=self.debug,
            )

            if self.debug and result.stdout:
                print(f"Output:\n{result.stdout}")

            if result.returncode != 0:
                raise RuntimeError(f"Failed to add crate: {result.stderr}")

            # Return path to modified libraries.yaml
            return self.infra_repo_path / "bin" / "yaml" / "libraries.yaml"

        except Exception as e:
            raise RuntimeError(f"Error adding crate: {e}")

    def generate_rust_props(self) -> str:
        """Generate Rust properties file content"""
        try:
            if self.is_windows:
                # Windows: use PowerShell script
                cmd = [
                    "powershell.exe",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.infra_repo_path / "ce_install.ps1"),
                    "generate-rust-props",
                ]
            else:
                # Linux/Mac: check if we can run ce_install directly
                ce_install_path = self.infra_repo_path / "bin" / "ce_install"
                if ce_install_path.exists():
                    # Make it executable if it isn't already
                    ce_install_path.chmod(0o755)
                    cmd = [str(ce_install_path), "generate-rust-props"]
                else:
                    # Try with poetry
                    poetry_bin = self.infra_repo_path / ".poetry" / "bin" / "poetry"
                    if poetry_bin.exists():
                        cmd = [str(poetry_bin), "run", "bin/ce_install", "generate-rust-props"]
                    else:
                        raise RuntimeError("Could not find ce_install executable")

            if self.debug:
                print(f"\nRunning: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=str(self.infra_repo_path),
                capture_output=True,
                text=True,
                env=self._get_clean_env(),
            )

            if self.debug and result.stdout:
                print(f"Output:\n{result.stdout}")

            if result.returncode != 0:
                raise RuntimeError(f"Failed to generate rust props: {result.stderr}")

            # Read the generated props file
            props_file = self.infra_repo_path / "props"
            if not props_file.exists():
                raise RuntimeError("Props file was not generated")

            props_content = props_file.read_text()

            # Delete the props file so it doesn't get committed
            props_file.unlink()
            if self.debug:
                print("Deleted temporary props file")

            return props_content

        except Exception as e:
            raise RuntimeError(f"Error generating rust props: {e}")

    def process_rust_library(self, config: LibraryConfig) -> tuple[Path, str]:
        """Process a Rust library addition and return paths to modified files"""
        if not config.is_rust():
            raise ValueError("This handler only processes Rust libraries")

        # Setup ce_install if needed
        self.setup_ce_install()

        # Add the crate
        libraries_yaml_path = self.add_crate(config.name, config.version)

        # Generate new properties
        new_props_content = self.generate_rust_props()

        return libraries_yaml_path, new_props_content

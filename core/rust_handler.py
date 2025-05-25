import subprocess
import platform
import os
from pathlib import Path
from typing import Tuple, Optional
from core.models import LibraryConfig


class RustLibraryHandler:
    """Handles Rust library additions using ce_install utilities"""
    
    def __init__(self, infra_repo_path: Path):
        self.infra_repo_path = infra_repo_path
        self.is_windows = platform.system() == "Windows"
        
    def setup_ce_install(self) -> bool:
        """Run make ce or ce_install.ps1 based on platform"""
        try:
            if self.is_windows:
                # Run PowerShell script on Windows
                cmd = ["powershell.exe", "-ExecutionPolicy", "Bypass", 
                       "-File", str(self.infra_repo_path / "ce_install.ps1")]
            else:
                # Run make ce on Linux/Mac
                cmd = ["make", "ce"]
            
            result = subprocess.run(
                cmd,
                cwd=str(self.infra_repo_path),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to setup ce_install: {result.stderr}")
            
            return True
            
        except Exception as e:
            raise RuntimeError(f"Error setting up ce_install: {e}")
    
    def add_crate(self, crate_name: str, version: str) -> Path:
        """Add a Rust crate using ce_install add-crate command"""
        try:
            if self.is_windows:
                # Windows: use PowerShell script
                cmd = [
                    "powershell.exe", "-ExecutionPolicy", "Bypass",
                    "-File", str(self.infra_repo_path / "ce_install.ps1"),
                    "add-crate", crate_name, version
                ]
            else:
                # Linux/Mac: use bin/ce_install
                ce_install_path = self.infra_repo_path / "bin" / "ce_install"
                cmd = [str(ce_install_path), "add-crate", crate_name, version]
            
            result = subprocess.run(
                cmd,
                cwd=str(self.infra_repo_path),
                capture_output=True,
                text=True
            )
            
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
                    "powershell.exe", "-ExecutionPolicy", "Bypass",
                    "-File", str(self.infra_repo_path / "ce_install.ps1"),
                    "generate-rust-props"
                ]
            else:
                # Linux/Mac: use bin/ce_install
                ce_install_path = self.infra_repo_path / "bin" / "ce_install"
                cmd = [str(ce_install_path), "generate-rust-props"]
            
            result = subprocess.run(
                cmd,
                cwd=str(self.infra_repo_path),
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Failed to generate rust props: {result.stderr}")
            
            # Read the generated props file
            props_file = self.infra_repo_path / "props"
            if not props_file.exists():
                raise RuntimeError("Props file was not generated")
            
            return props_file.read_text()
            
        except Exception as e:
            raise RuntimeError(f"Error generating rust props: {e}")
    
    def process_rust_library(self, config: LibraryConfig) -> Tuple[Path, str]:
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
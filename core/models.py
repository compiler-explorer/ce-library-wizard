from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, HttpUrl, field_validator


class Language(str, Enum):
    C = "C"
    CPP = "C++"
    RUST = "Rust"
    FORTRAN = "Fortran"
    JAVA = "Java"
    KOTLIN = "Kotlin"


class BuildTool(str, Enum):
    CMAKE = "cmake"
    MAKE = "make"


class LinkType(str, Enum):
    SHARED = "shared"
    STATIC = "static"


class LibraryType(str, Enum):
    HEADER_ONLY = "header-only"
    PACKAGED_HEADERS = "packaged-headers"
    STATIC = "static"
    SHARED = "shared"


class LibraryConfig(BaseModel):
    language: Language
    github_url: HttpUrl | None = None
    version: str | list[str]  # Support single version or list of versions
    is_header_only: bool | None = None
    build_tool: BuildTool | None = None
    link_type: LinkType | None = None
    binary_names: list[str] | None = None
    is_c_library: bool | None = None
    name: str | None = None  # For Rust crates
    library_type: LibraryType | None = None  # For C++ libraries
    library_id: str | None = None  # Library identifier for C++

    @field_validator("version")
    @classmethod
    def validate_version(cls, v):
        """Validate version field - convert comma-separated string to list"""
        if isinstance(v, str):
            # Check if it contains commas (multiple versions)
            if "," in v:
                versions = [ver.strip() for ver in v.split(",") if ver.strip()]
                if not versions:
                    raise ValueError("No valid versions found in comma-separated string")
                return versions
            else:
                # Single version string
                return v.strip()
        elif isinstance(v, list):
            # List of versions
            if not v:
                raise ValueError("Version list cannot be empty")
            return [ver.strip() for ver in v if ver.strip()]
        else:
            raise ValueError("Version must be a string or list of strings")

    def get_versions(self) -> list[str]:
        """Get list of versions, handling both single and multiple version cases"""
        if isinstance(self.version, str):
            return [self.version]
        return self.version

    def get_primary_version(self) -> str:
        """Get the primary (first) version for operations that need a single version"""
        versions = self.get_versions()
        return versions[0]

    def is_multi_version(self) -> bool:
        """Check if this config has multiple versions"""
        return isinstance(self.version, list) and len(self.version) > 1

    def is_c_or_cpp(self) -> bool:
        return self.language in [Language.C, Language.CPP]

    def requires_build_info(self) -> bool:
        return self.is_c_or_cpp() and self.is_header_only is False

    def is_rust(self) -> bool:
        return self.language == Language.RUST

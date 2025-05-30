from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, HttpUrl


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
    version: str
    is_header_only: bool | None = None
    build_tool: BuildTool | None = None
    link_type: LinkType | None = None
    binary_names: list[str] | None = None
    is_c_library: bool | None = None
    name: str | None = None  # For Rust crates
    library_type: LibraryType | None = None  # For C++ libraries
    library_id: str | None = None  # Library identifier for C++

    def is_c_or_cpp(self) -> bool:
        return self.language in [Language.C, Language.CPP]

    def requires_build_info(self) -> bool:
        return self.is_c_or_cpp() and self.is_header_only is False

    def is_rust(self) -> bool:
        return self.language == Language.RUST

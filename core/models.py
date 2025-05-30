from typing import Optional, List
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
    github_url: Optional[HttpUrl] = None
    version: str
    is_header_only: Optional[bool] = None
    build_tool: Optional[BuildTool] = None
    link_type: Optional[LinkType] = None
    binary_names: Optional[List[str]] = None
    is_c_library: Optional[bool] = None
    name: Optional[str] = None  # For Rust crates
    library_type: Optional[LibraryType] = None  # For C++ libraries
    library_id: Optional[str] = None  # Library identifier for C++

    def is_c_or_cpp(self) -> bool:
        return self.language in [Language.C, Language.CPP]

    def requires_build_info(self) -> bool:
        return self.is_c_or_cpp() and self.is_header_only is False
    
    def is_rust(self) -> bool:
        return self.language == Language.RUST
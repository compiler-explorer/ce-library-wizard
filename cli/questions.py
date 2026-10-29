import re
from pathlib import Path

import inquirer

from core.cpp_handler import CppHandler
from core.go_handler import (
    AmbiguousImportPathError,
    GoHandler,
    detect_import_path,
    is_package_in_module,
    resolve_go_module,
)
from core.library_utils import filter_main_cmake_targets
from core.models import BuildTool, Language, LibraryConfig, LibraryType, LinkType


def prompt(questions: list) -> dict:
    """inquirer.prompt, but let Ctrl-C reach main instead of returning None"""
    return inquirer.prompt(questions, raise_keyboard_interrupt=True)


def ask_go_import_path(ambiguity: AmbiguousImportPathError) -> str:
    """Ask which package to build when a Go module's root has none and there are several."""
    module_path = ambiguity.module_path
    print(f"\n{module_path} has no package at its root. Top-level packages:")
    for candidate in ambiguity.candidates:
        print(f"  {candidate}")

    def full_import_path(answer: str) -> str:
        answer = answer.strip().strip("/")
        if answer == module_path or answer.startswith(f"{module_path}/"):
            return answer
        return f"{module_path}/{answer}"

    question = [
        inquirer.Text(
            "import_path",
            message="Which package should be built? (import path, or path within the module)",
            validate=lambda _, x: bool(x.strip())
            and is_package_in_module(module_path, full_import_path(x), ambiguity.packages)
            or f"Not a package in {module_path}@{ambiguity.version}",
        )
    ]
    return full_import_path(prompt(question)["import_path"])


def ask_library_questions() -> LibraryConfig:
    """Ask user a series of questions to configure library addition"""

    # Question 1: Language
    language_question = [
        inquirer.List(
            "language",
            message="For what language do you want to add the library?",
            choices=[lang.value for lang in Language],
        )
    ]
    language_answer = prompt(language_question)
    language = Language(language_answer["language"])

    # Special handling for Rust - only need name and version
    if language == Language.RUST:
        rust_name_question = [
            inquirer.Text(
                "name",
                message="What's the name of the Rust crate?",
                validate=lambda _, x: len(x.strip()) > 0,
            )
        ]
        rust_name_answer = prompt(rust_name_question)

        rust_version_question = [
            inquirer.Text(
                "version",
                message="What's the version(s) of the crate? (comma-separated for multiple)",
                validate=lambda _, x: len(x.strip()) > 0,
            )
        ]
        rust_version_answer = prompt(rust_version_question)

        config = LibraryConfig(
            language=language, name=rust_name_answer["name"], version=rust_version_answer["version"]
        )
        return config

    # Special handling for Go - need module path and version
    if language == Language.GO:
        go_module_question = [
            inquirer.Text(
                "module",
                message="What's the Go module path? (e.g., github.com/google/uuid)",
                validate=lambda _, x: len(x.strip()) > 0 and "/" in x,
            )
        ]
        go_module_answer = prompt(go_module_question)

        go_version_question = [
            inquirer.Text(
                "version",
                message="What's the version(s)? (e.g., v1.6.0, comma-separated for multiple)",
                validate=lambda _, x: len(x.strip()) > 0,
            )
        ]
        go_version_answer = prompt(go_version_question)

        module_path = go_module_answer["module"]
        version_str = go_version_answer["version"]
        first_version = version_str.split(",")[0].strip()

        print("\nResolving module path...")
        resolved_module, resolved_import = resolve_go_module(module_path, first_version)
        if resolved_module != module_path:
            print(f"Using module path {resolved_module} (entered: {module_path})")
            if resolved_import:
                print(f"  import path: {resolved_import}")
            module_path = resolved_module

        suggested_id = GoHandler.suggest_library_id_static(module_path)

        go_id_question = [
            inquirer.Text(
                "library_id",
                message="What should be the library ID? (lowercase with underscores)",
                default=suggested_id,
                validate=lambda _, x: bool(re.match(r"^[a-z][a-z0-9_]*$", x.strip()))
                or "Must start with a letter, lowercase alphanumeric and underscores only",
            )
        ]
        go_id_answer = prompt(go_id_question)

        import_path = resolved_import
        if not import_path:
            print("\nChecking module structure...")
            try:
                import_path = detect_import_path(module_path, first_version)
            except AmbiguousImportPathError as e:
                import_path = ask_go_import_path(e)
            else:
                if import_path:
                    print(f"No package at the module root, using the only candidate {import_path}")
                else:
                    print("Root package is importable")

        config = LibraryConfig(
            language=language,
            module=module_path,
            version=version_str,
            library_id=go_id_answer["library_id"],
            import_path=import_path,
        )
        return config

    # For non-Rust/Go languages, ask for GitHub URL
    github_question = [
        inquirer.Text(
            "github_url",
            message="What's the GitHub address of the library?",
            validate=lambda _, x: x.startswith("https://github.com/"),
        )
    ]
    github_answer = prompt(github_question)

    # Question 3: Version
    version_question = [
        inquirer.Text(
            "version",
            message=(
                "What's the version(s) of library that you want to add? "
                "(comma-separated for multiple)"
            ),
            validate=lambda _, x: len(x.strip()) > 0,
        )
    ]
    version_answer = prompt(version_question)

    # Initialize config with basic info
    config_data = {
        "language": language,
        "github_url": github_answer["github_url"],
        "version": version_answer["version"],
    }

    # C++ specific questions
    if language == Language.CPP:
        suggested_id = CppHandler.suggest_library_id_static(github_answer["github_url"])

        library_id_question = [
            inquirer.Text(
                "library_id",
                message="What should be the library ID? (lowercase with underscores)",
                default=suggested_id,
                validate=lambda _, x: CppHandler.validate_library_id_static(x)
                or "Must be lowercase letters, numbers, and underscores only",
            )
        ]
        library_id_answer = prompt(library_id_question)
        config_data["library_id"] = library_id_answer["library_id"]

        print("\nAnalyzing repository to detect library type...")
        cpp_handler = CppHandler(Path.home(), setup_ce_install=False, debug=False)
        is_valid, detected_type, cmake_targets, check_file = cpp_handler.detect_library_type(
            github_answer["github_url"], library_id_answer["library_id"]
        )

        if not is_valid:
            print("⚠️  Could not automatically detect library type.")
            detected_type = None
        else:
            print(f"✓ Detected library type: {detected_type.value if detected_type else 'Unknown'}")
            if cmake_targets:
                main_targets = filter_main_cmake_targets(cmake_targets)
                if main_targets:
                    print(
                        f"✓ Found {len(main_targets)} CMake targets for linking: "
                        f"{', '.join(main_targets[:3])}"
                        + (f" and {len(main_targets)-3} more" if len(main_targets) > 3 else "")
                    )

        # Ask about library type with detected value as default
        library_type_choices = [
            LibraryType.HEADER_ONLY.value,
            LibraryType.PACKAGED_HEADERS.value,
            LibraryType.STATIC.value,
            LibraryType.SHARED.value,
        ]

        library_type_question = [
            inquirer.List(
                "library_type",
                message="What type of library is this?",
                choices=library_type_choices,
                default=detected_type.value
                if detected_type
                else LibraryType.PACKAGED_HEADERS.value,
            )
        ]
        library_type_answer = prompt(library_type_question)
        config_data["library_type"] = LibraryType(library_type_answer["library_type"])
        if check_file:
            config_data["check_file"] = check_file

        # Set package installation based on library type
        selected_type = LibraryType(library_type_answer["library_type"])
        if selected_type == LibraryType.PACKAGED_HEADERS:
            # packaged-headers always uses package installation
            config_data["package_install"] = True
            print("✓ Using CMake package installation (default for packaged-headers)")
        elif cmake_targets:
            # Ask about package installation for other library types with CMake
            package_install_question = [
                inquirer.Confirm(
                    "package_install",
                    message=(
                        "Do the headers need to be configured and installed by CMake? "
                        "(Choose 'Yes' if headers require CMake processing, 'No' if usable as-is)"
                    ),
                    default=False,
                )
            ]
            package_install_answer = prompt(package_install_question)
            config_data["package_install"] = package_install_answer["package_install"]

        # Headers are used straight from the repository, so ask where they live
        if not config_data.get("package_install"):
            if not (check_file or "").startswith("include/"):
                print("⚠️  No include/ directory with headers found in the repository.")
            include_path_question = [
                inquirer.Text(
                    "include_path",
                    message=(
                        "Header directory relative to the repository root " "('.' for the root)"
                    ),
                    default="include",
                )
            ]
            include_path_answer = prompt(include_path_question)
            # LibraryConfig normalizes and validates the path
            if include_path_answer["include_path"] != "include":
                config_data["include_path"] = include_path_answer["include_path"]

    # C/C++ specific questions
    elif language in [Language.C, Language.CPP]:
        # Question 4: Header-only?
        header_only_question = [
            inquirer.Confirm(
                "is_header_only", message="Is this library header-only?", default=False
            )
        ]
        header_only_answer = prompt(header_only_question)
        config_data["is_header_only"] = header_only_answer["is_header_only"]

        if not header_only_answer["is_header_only"]:
            # Question 5: Build tool
            build_tool_question = [
                inquirer.List(
                    "build_tool",
                    message="What build tool does it support?",
                    choices=[tool.value for tool in BuildTool],
                )
            ]
            build_tool_answer = prompt(build_tool_question)
            config_data["build_tool"] = BuildTool(build_tool_answer["build_tool"])

            # Question 6: Link type and binary names
            link_type_question = [
                inquirer.List(
                    "link_type",
                    message="Should the library produce shared or static binaries?",
                    choices=[link.value for link in LinkType],
                )
            ]
            link_type_answer = prompt(link_type_question)
            config_data["link_type"] = LinkType(link_type_answer["link_type"])

            binary_names_question = [
                inquirer.Text(
                    "binary_names",
                    message="What are the names of the binaries to link against? (comma-separated)",
                    validate=lambda _, x: len(x.strip()) > 0,
                )
            ]
            binary_names_answer = prompt(binary_names_question)
            config_data["binary_names"] = [
                name.strip() for name in binary_names_answer["binary_names"].split(",")
            ]

        # Question 7: C++ specific - is it really C?
        if language == Language.CPP:
            is_c_library_question = [
                inquirer.Confirm(
                    "is_c_library",
                    message="Is this actually a C library that can be shared between C and C++?",
                    default=False,
                )
            ]
            is_c_library_answer = prompt(is_c_library_question)
            config_data["is_c_library"] = is_c_library_answer["is_c_library"]

    # Create the config and normalize versions with git lookup
    config = LibraryConfig(**config_data)

    config.validate_versions_and_exit_on_missing()

    return config

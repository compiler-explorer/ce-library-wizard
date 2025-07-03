import inquirer

from core.models import BuildTool, Language, LibraryConfig, LibraryType, LinkType


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
    language_answer = inquirer.prompt(language_question)
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
        rust_name_answer = inquirer.prompt(rust_name_question)

        rust_version_question = [
            inquirer.Text(
                "version",
                message="What's the version(s) of the crate? (comma-separated for multiple)",
                validate=lambda _, x: len(x.strip()) > 0,
            )
        ]
        rust_version_answer = inquirer.prompt(rust_version_question)

        return LibraryConfig(
            language=language, name=rust_name_answer["name"], version=rust_version_answer["version"]
        )

    # For non-Rust languages, ask for GitHub URL
    github_question = [
        inquirer.Text(
            "github_url",
            message="What's the GitHub address of the library?",
            validate=lambda _, x: x.startswith("https://github.com/"),
        )
    ]
    github_answer = inquirer.prompt(github_question)

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
    version_answer = inquirer.prompt(version_question)

    # Initialize config with basic info
    config_data = {
        "language": language,
        "github_url": github_answer["github_url"],
        "version": version_answer["version"],
    }

    # C++ specific questions
    if language == Language.CPP:
        # First, ask for library ID
        from core.cpp_handler import CppHandler

        # Use a temporary instance just for ID suggestion (no path needed)
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
        library_id_answer = inquirer.prompt(library_id_question)
        config_data["library_id"] = library_id_answer["library_id"]

        # Detect library type by cloning and checking
        print("\nAnalyzing repository to detect library type...")
        # Create a temporary handler just for detection (no ce_install setup needed)
        from pathlib import Path

        cpp_handler = CppHandler(Path.home(), setup_ce_install=False, debug=False)
        is_valid, detected_type = cpp_handler.detect_library_type(github_answer["github_url"])

        if not is_valid:
            print("⚠️  Could not automatically detect library type.")
            detected_type = None
        else:
            print(f"✓ Detected library type: {detected_type.value if detected_type else 'Unknown'}")

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
        library_type_answer = inquirer.prompt(library_type_question)
        config_data["library_type"] = LibraryType(library_type_answer["library_type"])

    # C/C++ specific questions
    elif language in [Language.C, Language.CPP]:
        # Question 4: Header-only?
        header_only_question = [
            inquirer.Confirm(
                "is_header_only", message="Is this library header-only?", default=False
            )
        ]
        header_only_answer = inquirer.prompt(header_only_question)
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
            build_tool_answer = inquirer.prompt(build_tool_question)
            config_data["build_tool"] = BuildTool(build_tool_answer["build_tool"])

            # Question 6: Link type and binary names
            link_type_question = [
                inquirer.List(
                    "link_type",
                    message="Should the library produce shared or static binaries?",
                    choices=[link.value for link in LinkType],
                )
            ]
            link_type_answer = inquirer.prompt(link_type_question)
            config_data["link_type"] = LinkType(link_type_answer["link_type"])

            binary_names_question = [
                inquirer.Text(
                    "binary_names",
                    message="What are the names of the binaries to link against? (comma-separated)",
                    validate=lambda _, x: len(x.strip()) > 0,
                )
            ]
            binary_names_answer = inquirer.prompt(binary_names_question)
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
            is_c_library_answer = inquirer.prompt(is_c_library_question)
            config_data["is_c_library"] = is_c_library_answer["is_c_library"]

    return LibraryConfig(**config_data)

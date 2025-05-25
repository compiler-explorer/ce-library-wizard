# CE Library Wizard

A CLI tool to simplify adding libraries to [Compiler Explorer](https://godbolt.org/).

## Features

- Interactive CLI for adding libraries to Compiler Explorer
- Special support for Rust crates with automated `ce_install` integration
- Automatic git repository management and PR creation
- Cross-platform support (Linux, macOS, Windows)

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Basic usage
ce-lib-wizard

# With GitHub token for PR creation
export GITHUB_TOKEN=your_github_token
ce-lib-wizard

# Debug mode
ce-lib-wizard --debug
```

## Supported Languages

Currently supported:
- **Rust** - Fully automated using `ce_install` utilities

Planned support:
- C
- C++
- Fortran
- Java
- Kotlin

## How it Works

### For Rust Libraries

1. Prompts for crate name and version
2. Clones the `compiler-explorer/infra` repository
3. Runs `make ce` (or `ce_install.ps1` on Windows)
4. Uses `ce_install add-crate` to add the library
5. Generates updated Rust properties using `ce_install generate-rust-props`
6. Updates `rust.amazon.properties` in the main repository
7. Creates pull requests to both repositories (if GitHub token provided)

## Requirements

- Python 3.8+
- Git
- Make (for Linux/macOS) or PowerShell (for Windows)

## License

MIT
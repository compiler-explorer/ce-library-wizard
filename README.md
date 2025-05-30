# CE Library Wizard

A CLI tool that automates the process of adding libraries to [Compiler Explorer](https://compiler-explorer.com/). It handles repository forking, library detection, properties generation, and pull request creation - making library contributions quick and error-free.

## Features

- 🚀 Interactive CLI for adding libraries to Compiler Explorer
- 🦀 **Rust support** - Fully automated with `ce_install` integration
- ⚡ **C++ support** - Automated library detection and properties generation
- 🔐 Multiple authentication methods (OAuth, GitHub CLI, Personal Access Token)
- 🍴 Automatic forking of repositories for users without write access
- 📝 Preview changes with `--verify` flag before committing
- 🎯 Command-line arguments for automation
- 🔍 Debug mode with comprehensive logging
- 🌍 Cross-platform support (Linux, macOS, Windows)

## Installation

```bash
# Clone the repository
git clone https://github.com/compiler-explorer/ce-lib-wizard.git
cd ce-lib-wizard

# Run directly with the provided script (handles Poetry installation)
./run.sh
```

### Manual Installation

If you prefer to install manually:

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Run the tool
poetry run ce-lib-wizard
```

## Usage

### Interactive Mode

```bash
# Basic interactive usage
./run.sh

# With OAuth authentication (opens browser)
./run.sh --oauth

# With GitHub token
export GITHUB_TOKEN=your_github_token
./run.sh

# Preview changes before committing
./run.sh --verify
```

### Command-Line Mode

```bash
# Add a Rust library directly
./run.sh --lang=rust --lib=ahash --ver=0.8.12

# Add a C++ library from GitHub
./run.sh --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1

# With OAuth authentication
./run.sh --oauth --lang=rust --lib=ahash --ver=0.8.12

# Preview changes
./run.sh --verify --lang=cpp --lib=https://github.com/nlohmann/json --ver=3.11.3

# Debug mode
./run.sh --debug --lang=rust --lib=ahash --ver=0.8.12
```

## Authentication Methods

The tool supports three authentication methods:

1. **OAuth (Browser-based)**
   ```bash
   ./run.sh --oauth
   ```
   - Opens your browser for GitHub authentication
   - No need to create or manage tokens
   - Uses a local server on port 8745

2. **GitHub CLI**
   - If you have `gh` installed and authenticated, the tool will use it automatically

3. **Personal Access Token**
   ```bash
   export GITHUB_TOKEN=your_token
   ./run.sh
   ```

## Supported Languages

Currently supported:
- **Rust** - Fully automated using `ce_install` utilities
- **C++** - Automated library detection and properties generation

Planned support:
- C
- Fortran
- Java
- Kotlin

## How it Works

### For Rust Libraries

1. **Authentication** - Authenticates with GitHub (if token/OAuth provided)
2. **Forking** - Automatically creates or uses existing forks of:
   - `compiler-explorer/compiler-explorer`
   - `compiler-explorer/infra`
3. **Setup** - Clones repositories and sets up Poetry environment
4. **Library Addition**:
   - Runs `make ce` to set up the infra environment
   - Uses `ce_install add-crate` to add the library to `libraries.yaml`
   - Generates updated properties with `ce_install generate-rust-props`
5. **File Updates**:
   - Updates `bin/yaml/libraries.yaml` in the infra repository
   - Updates `etc/config/rust.amazon.properties` in the main repository (only the libs section)
6. **Review** (optional) - Shows diffs with `--verify` flag
7. **Commit & Push** - Commits changes and pushes to your fork
8. **Pull Requests** - Creates PRs from your fork to the upstream repositories

### For C++ Libraries

1. **Authentication** - Authenticates with GitHub (if token/OAuth provided)
2. **Forking** - Automatically creates or uses existing forks of:
   - `compiler-explorer/compiler-explorer`
   - `compiler-explorer/infra`
3. **Setup** - Clones repositories and sets up environment
4. **Library Detection**:
   - Detects library type by checking for CMakeLists.txt (defaults to packaged-headers)
   - Validates and suggests library ID following lowercase_with_underscores convention
5. **Library Addition**:
   - Uses `ce_install cpp-library add` to add the library to `libraries.yaml`
   - Generates properties with `ce_install generate-linux-props` and `generate-windows-props`
6. **File Updates**:
   - Updates `bin/yaml/libraries.yaml` in the infra repository
   - Updates C++ properties files in the main repository
7. **Review** (optional) - Shows diffs with `--verify` flag
8. **Commit & Push** - Commits changes and pushes to your fork
9. **Pull Requests** - Creates PRs from your fork to the upstream repositories

## Command-Line Options

- `--oauth` - Authenticate via browser using GitHub OAuth
- `--verify` - Show git diff of changes before committing
- `--debug` - Enable debug mode with verbose output
- `--github-token TOKEN` - Specify GitHub token directly
- `--lang LANGUAGE` - Specify the language (c, cpp, rust, fortran, java, kotlin)
- `--lib NAME` - Library name (for Rust) or GitHub URL (for C++)
- `--ver VERSION` - Library version

## Requirements

- Python 3.8+
- Git
- Make (for Linux/macOS) or PowerShell (for Windows)
- Internet connection for cloning repositories
- Poetry (automatically installed by `run.sh` if not present)

## Security Notes

- The tool uses OAuth for secure authentication
- Tokens are never stored locally
- All operations happen in temporary directories
- Fork-based workflow ensures you only push to your own repositories

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT
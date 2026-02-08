# Quick Start Guide

Get up and running with CE Library Wizard in minutes.

## Installation

```bash
# Clone the repository
git clone https://github.com/compiler-explorer/ce-lib-wizard.git
cd ce-lib-wizard

# Run the wizard (installs dependencies automatically)
./run.sh
```

## Basic Usage

### Interactive Mode
Simply run the tool and follow the prompts:
```bash
./run.sh
```

### Command-Line Mode
Skip the interactive prompts by providing all options:

**Rust library:**
```bash
./run.sh --lang=rust --lib=serde --ver=1.0.195
```

**C library:**
```bash
./run.sh --lang=c --lib=https://github.com/libuv/libuv --ver=1.46.0
```

**C++ library:**
```bash
./run.sh --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1
```

**Fortran library:**
```bash
./run.sh --lang=fortran --lib=https://github.com/jacobwilliams/json-fortran --ver=8.5.0
```

## Authentication Setup

For the best experience, set up GitHub CLI:

```bash
# Install GitHub CLI
brew install gh  # macOS
sudo apt-get install gh  # Ubuntu/Debian

# Authenticate
gh auth login
```

## Useful Options

### Preview Changes
See what will be modified before committing:
```bash
./run.sh --verify --lang=rust --lib=tokio --ver=1.35.0
```

### Debug Mode
Get detailed output for troubleshooting:
```bash
./run.sh --debug --lang=cpp --lib=https://github.com/nlohmann/json --ver=3.11.3
```

### Specify Library Type (C/C++ only)
Skip automatic detection and specify the library type directly:
```bash
# Header-only library
./run.sh --lang=cpp --lib=https://github.com/bobluppes/graaf --ver=v1.1.1 --type=header-only

# Packaged headers library  
./run.sh --lang=cpp --lib=https://github.com/eigen/eigen --ver=3.4.0 --type=packaged-headers

# Shared library (requires compilation)
./run.sh --lang=c --lib=https://github.com/curl/curl --ver=8.5.0 --type=cshared
```

Valid types: `header-only`, `packaged-headers`, `static`, `shared`, `cshared`

### CMake Package Installation (C/C++ only)
For libraries that require CMake configuration of headers:
```bash
# Manual flag for static/shared libraries that need CMake package installation
./run.sh --lang=cpp --lib=https://github.com/microsoft/vcpkg --ver=2024.01.12 --type=static --package-install

# Note: packaged-headers libraries automatically use package installation
./run.sh --lang=cpp --lib=https://github.com/eigen/eigen --ver=3.4.0 --type=packaged-headers
```

### Test Installation (C/C++ only)
Validate that the library installs correctly:
```bash
./run.sh --install-test --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1
```

### Test Build (C/C++/Rust/Fortran)
Test building the library and verify artifacts are produced correctly.
Requires a compiler installed via `ce_install`:

**C/C++ libraries** (requires gcc or clang):
```bash
./run.sh --build-test=yes --lang=cpp --lib=https://github.com/madler/zlib --ver=1.3.1
```

**Rust crates** (requires Rust compiler):
```bash
./run.sh --build-test=yes --lang=rust --lib=serde --ver=1.0.219
```

**Fortran libraries** (requires gfortran via gcc):
```bash
./run.sh --build-test=yes --lang=fortran --lib=https://github.com/jacobwilliams/json-fortran --ver=8.3.0
```

Build test modes:
- `auto` (default): Run if a compiler is available and the library type requires building
- `yes`: Force run build test (fails if no compiler available)
- `no`: Skip build test entirely

Note: Header-only libraries are automatically skipped in `auto` mode since they don't require compilation.

This will:
- Auto-detect the latest installed compiler (prefers gfortran for Fortran)
- Build the library in a staging directory
- List all artifacts produced (libraries, headers, .rlib files, Fortran modules, etc.)
- For C/C++: Verify that expected link libraries (from `staticliblink`/`sharedliblink` config) are present

### Dry Run Mode
Preview all changes without committing or creating PRs:
```bash
./run.sh --dry-run --lang=rust --lib=serde --ver=1.0.219
```

### Skip Confirmation Prompts
Use `-y` or `--yes` to skip confirmation prompts (useful for automation):
```bash
./run.sh -y --lang=rust --lib=serde --ver=1.0.219
```

### Keep Temporary Files
For debugging, keep the temporary directories after the tool exits:
```bash
./run.sh --keep-temp --lang=rust --lib=serde --ver=1.0.195
```

### Add Multiple Versions
Add multiple versions of the same library in one operation:
```bash
./run.sh --lang=rust --lib=serde --ver=1.0.193,1.0.194,1.0.195
```

### Add Top 100 Rust Crates
Add the most popular Rust crates in bulk:
```bash
./run.sh --top-rust-crates
```

## What Happens Next?

1. The tool clones the necessary repositories
2. Creates feature branches for your changes
3. Runs the appropriate `ce_install` commands
4. Updates configuration files
5. Commits changes to your fork
6. Creates pull requests to the upstream repositories

## Common Workflows

### Adding Multiple Libraries
```bash
# Add several Rust crates
for crate in serde tokio async-trait; do
    ./run.sh --lang=rust --lib=$crate --ver=latest
done
```

### Checking Your PRs
After running the tool:
1. Check the URLs printed in the output
2. Review the PRs on GitHub
3. Wait for maintainer review

## Next Steps

- Read the [full documentation](../README.md) for more features
- Check [troubleshooting](troubleshooting.md) if you encounter issues
- Learn about [advanced usage](advanced-usage.md) for automation
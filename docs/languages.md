# Language-Specific Documentation

This document provides detailed information about how CE Library Wizard handles each supported language.

## C Libraries

### Overview
C library support uses the same infrastructure as C++ libraries, leveraging `ce_install cpp-library` commands to add libraries to both `c.amazon.properties` and `libraries.yaml`.

### Process
1. **Library Addition**: Uses `ce_install cpp-library add` to add the library to `libraries.yaml`
2. **Property Generation**: Runs `ce_install generate-linux-props` to update `c.amazon.properties`
3. **File Updates**:
   - `bin/yaml/libraries.yaml` in the infra repository
   - `etc/config/c.amazon.properties` in the main repository

### Example
```bash
./run.sh --lang=c --lib=https://github.com/libuv/libuv --ver=1.46.0
```

### Library Types
- **shared**: Shared libraries that need to be linked at runtime
- **header-only**: Header-only libraries without compilation requirements
- **static**: Static libraries linked at compile time

## Rust Libraries

### Overview
Rust library support is fully automated using Compiler Explorer's `ce_install` utilities.

### Process
1. **Library Addition**: Uses `ce_install add-crate` to add the library to `libraries.yaml`
2. **Property Generation**: Runs `ce_install generate-rust-props` to create properties
3. **File Updates**:
   - `bin/yaml/libraries.yaml` in the infra repository
   - `etc/config/rust.amazon.properties` in the main repository (libs section only)

### Examples
```bash
# Single crate
./run.sh --lang=rust --lib=serde --ver=1.0.195

# Multiple versions
./run.sh --lang=rust --lib=serde --ver=1.0.193,1.0.194,1.0.195

# Top 100 Rust crates (bulk addition)
./run.sh --top-rust-crates
```

### Bulk Operations
The tool supports adding the top 100 Rust crates using the `add-top-rust-crates` ce_install command:
- Adds approximately 100 popular crates from crates.io
- Creates a single large PR for all crates
- Includes proper versioning and dependency information

### Requirements
- Valid crate name from crates.io
- Semantic version number

## C++ Libraries

### Overview
C++ support includes automatic library type detection and comprehensive property generation.

### Library Types
- **packaged-headers**: Libraries with CMakeLists.txt that need compilation
- **header-only**: Header-only libraries without build requirements

### Process
1. **Type Detection**: Clones repository and checks for CMakeLists.txt
2. **ID Generation**: Converts GitHub URL to valid library ID (e.g., `fmtlib/fmt` → `fmt`)
3. **Library Addition**: Uses `ce_install cpp-library add`
4. **Property Generation**: 
   - Linux properties with `generate-linux-props`
   - Windows properties with `generate-windows-props`

### Installation Testing
The `--install-test` flag validates that the library can be installed:
```bash
./run.sh --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1 --install-test
```

Requirements:
- Linux or macOS only
- `/opt/compiler-explorer` directory with write permissions

### Examples
```bash
# Basic addition
./run.sh --lang=cpp --lib=https://github.com/nlohmann/json --ver=3.11.3

# Multiple versions
./run.sh --lang=cpp --lib=https://github.com/nlohmann/json --ver=3.11.1,3.11.2,3.11.3

# With installation test
./run.sh --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1 --install-test
```

## Fortran Libraries

### Overview
Fortran support is designed for FPM (Fortran Package Manager) packages.

### Requirements
- Repository must contain `fpm.toml` file
- Valid FPM package structure

### Process
1. **Validation**: Clones repository and verifies `fpm.toml` exists
2. **Library Addition**: Uses `ce_install fortran-library add`
3. **Property Updates**:
   - Adds library to `libs=` line in properties
   - Creates library-specific property entries

### Examples
```bash
# Single version
./run.sh --lang=fortran --lib=https://github.com/jacobwilliams/json-fortran --ver=8.5.0

# Multiple versions
./run.sh --lang=fortran --lib=https://github.com/jacobwilliams/json-fortran --ver=8.4.0,8.5.0
```

### Property File Format
```properties
libs=json-fortran:roots-fortran

libs.json-fortran.url=https://github.com/jacobwilliams/json-fortran
libs.json-fortran.versions=8.5.0:8.4.0
```

## Library ID Conventions

All languages follow these naming conventions:
- Lowercase letters, numbers, and underscores only
- Must start with a letter
- Convert hyphens to underscores
- Remove special characters

Examples:
- `fmt-lib` → `fmt_lib`
- `JSON-for-Modern-C++` → `json_for_modern_cpp`
- `boost-asio` → `boost_asio`

## Version Requirements

### Single Version Format
Preferred format: `MAJOR.MINOR.PATCH`
- Examples: `1.0.0`, `2.3.1`, `10.2.1`

### Multiple Version Format
Comma-separated versions:
- Examples: `1.0.0,1.0.1,1.0.2`
- Interactive: Enter versions separated by commas
- CLI flag: `--ver=1.0.0,1.0.1,1.0.2`

### Other Supported Formats
- Prefixed versions: `v1.0.0`
- Date-based: `2024.01.15`
- Git references: `main`, `develop`
- Commit hashes: `abc123def456`

### Multi-Version Processing
When multiple versions are specified:
- Each version is processed sequentially
- Individual PRs are created for each version
- Progress is shown for each version
- If one version fails, the process continues with remaining versions

## Property File Management

### File Locations
- C++: `etc/config/c++.amazon.properties`
- Rust: `etc/config/rust.amazon.properties`
- Fortran: `etc/config/fortran.amazon.properties`

### Update Process
1. Properties are generated/updated automatically
2. The `libs=` line is updated to include new libraries
3. Version-specific entries are added

## Adding Support for New Languages

To add a new language:

1. Create a handler class in `core/{language}_handler.py`
2. Update the `Language` enum in `core/models.py`
3. Add processing function in `cli/main.py`
4. Update CLI argument choices
5. Document the requirements and process

See the [Contributing Guide](contributing.md) for detailed instructions.
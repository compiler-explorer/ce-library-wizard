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

## Go Libraries

### Overview
Go support handles Go modules that are built using the `gomod` build type. Libraries are identified by their Go module path (e.g., `github.com/google/uuid`).

### Requirements
- Valid Go module path
- Version must be a valid Go module version (typically with `v` prefix, e.g., `v1.6.0`)
- Module must be available on the Go module proxy (proxy.golang.org)

### Process
1. **Library Addition**: Adds the module to `libraries.yaml` with `build_type: gomod`
2. **Property Updates**:
   - Adds library to `libs=` line in `go.amazon.properties`
   - Creates library-specific property entries with `lookupname`, `packagedheaders=true`

### Import Path Override
Some Go modules have a non-importable root package (e.g., `google.golang.org/protobuf`). In these cases, the wizard:
1. **Auto-detects** the best importable subpackage by downloading the module zip from the Go proxy
2. Sets the `import_path` field in `libraries.yaml` (e.g., `google.golang.org/protobuf/proto`)

You can also manually specify the import path with `--import-path`:
```bash
./run.sh --lang=go --lib=google.golang.org/protobuf --ver=v1.36.0 --import-path=google.golang.org/protobuf/proto
```

### Subpackage Path Resolution
If you pass a subpackage path as `--lib` (e.g., `google.golang.org/protobuf/proto`), the wizard automatically resolves it to the actual module root (`google.golang.org/protobuf`) and sets the original path as the `import_path`.

### Examples
```bash
# Single version
./run.sh --lang=go --lib=github.com/google/uuid --ver=v1.6.0

# Multiple versions
./run.sh --lang=go --lib=google.golang.org/protobuf --ver=v1.34.1,v1.36.0

# With explicit import path
./run.sh --lang=go --lib=google.golang.org/protobuf --ver=v1.36.0 --import-path=google.golang.org/protobuf/proto

# Passing a subpackage path (auto-resolves to module root)
./run.sh --lang=go --lib=google.golang.org/protobuf/proto --ver=v1.36.0
```

### Property File Format
```properties
libs=uuid:protobuf:errors

libs.uuid.name=google/uuid
libs.uuid.url=https://github.com/google/uuid
libs.uuid.lookupname=go_uuid
libs.uuid.packagedheaders=true
libs.uuid.versions=v160
libs.uuid.versions.v160.version=v1.6.0
```

### libraries.yaml Format
```yaml
go:
  uuid:
    build_type: gomod
    module: github.com/google/uuid
    targets:
    - v1.6.0
    type: gomod
  protobuf:
    build_type: gomod
    import_path: google.golang.org/protobuf/proto
    module: google.golang.org/protobuf
    targets:
    - v1.36.0
    type: gomod
```

### Key Differences from Other Languages
- Uses Go module path instead of GitHub URL for identification
- All Go libraries use `packagedheaders=true`
- Uses `lookupname` with `go_` prefix (e.g., `go_uuid`)
- No `staticliblink` or `path` fields needed
- Version keys strip non-alphanumeric characters (e.g., `v1.6.0` -> `v160`)

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
- Go: `etc/config/go.amazon.properties`

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
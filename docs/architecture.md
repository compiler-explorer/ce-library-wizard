# Architecture & Internal Workings

This document explains the internal architecture and design decisions of CE Library Wizard.

## Overview

CE Library Wizard automates the complex process of adding libraries to Compiler Explorer by managing two separate repositories, running build tools, and creating pull requests. The tool is designed with a clean separation of concerns to support both CLI usage and potential future API deployments.

## Directory Structure

```
ce-lib-wizard/
├── core/                    # Business logic (pure functions, no I/O)
│   ├── models.py           # Data models (Pydantic)
│   ├── git_operations.py   # Git repository management
│   ├── github_auth.py      # Authentication handling
│   ├── subprocess_utils.py # Process execution utilities
│   ├── library_utils.py    # Shared library functions
│   ├── constants.py        # Shared strings and messages
│   ├── ui_utils.py         # Shared UI functions
│   ├── cpp_handler.py      # C++ library logic
│   ├── c_handler.py        # C library logic
│   ├── rust_handler.py     # Rust library logic
│   ├── fortran_handler.py  # Fortran library logic
│   └── file_modifications.py # File update logic
├── cli/                     # CLI-specific code
│   ├── main.py             # Entry point and orchestration
│   └── questions.py        # Interactive prompts
├── docs/                    # Documentation
├── run.sh                   # Shell wrapper (handles Poetry)
└── pyproject.toml          # Python dependencies
```

## Design Principles

### 1. Separation of Concerns
- **Core**: Pure business logic with no direct I/O operations
- **CLI**: Handles user interaction, argument parsing, and output formatting
- **Handlers**: Language-specific logic encapsulated in separate classes

### 2. Dependency Injection
External services (like file systems and processes) are injected into core functions, making them testable and reusable.

### 3. Fail-Safe Operations
The tool operates in temporary directories and only modifies user-owned forks, preventing accidental damage to upstream repositories.

## Key Components

### Shared Library Utilities (core/library_utils.py)
Centralized functions used by both C and C++ handlers:
- `clone_and_analyze_repository()`: Repository cloning and analysis
- `detect_library_type_from_analysis()`: Library type detection logic
- `get_cmake_targets_from_path()`: CMake target discovery
- `filter_main_cmake_targets()`: Target filtering (excludes test/doc targets)
- `build_ce_install_command()`: Centralized command building
- `check_ce_install_link_support()`: Feature detection for infra version

### GitManager (core/git_operations.py)
Manages all Git operations using context manager pattern:
- Clones repositories to temporary directories
- Creates and manages feature branches
- Handles commits and pushes
- Creates pull requests via GitHub API

```python
with GitManager(github_token) as git_mgr:
    main_repo, infra_repo = git_mgr.clone_repositories()
    # ... operations ...
```

### Language Handlers
Each supported language has its own handler class:

#### CppHandler
- Detects library type (header-only, packaged-headers, static, shared, cshared)
- Checks existing configuration in libraries.yaml (local and remote)
- Performs git tag lookup to determine version format and target_prefix
- Automatically detects CMake targets for static/shared libraries
- Runs `ce_install cpp-library add` with appropriate flags
- Supports `--package-install` flag for CMake header configuration
- Generates Linux and Windows properties
- Validates library paths

#### CHandler
- Handles C libraries with similar logic to C++
- Supports same library types as C++ (static, shared, cshared)
- Uses shared utilities from library_utils.py
- Integrates with ce_install for library addition

#### RustHandler
- Uses `ce_install add-crate`
- Generates Rust properties
- Updates the libs section in properties file

#### FortranHandler
- Validates FPM packages (requires fpm.toml)
- Updates both libraries.yaml and fortran.amazon.properties
- Manages the libs= line in properties

### Authentication Flow

```
User Input
    ↓
1. Check GITHUB_TOKEN env var
2. Try GitHub CLI (gh auth status)
3. Offer OAuth option (--oauth flag)
    ↓
Selected Method
    ↓
GitManager uses token for API calls
```

### OAuth Implementation
- Local server on port 8745
- CSRF protection with state parameter
- Automatic browser opening
- Token used only for session duration

## Dual Repository Workflow

Compiler Explorer requires updates to two repositories:

### 1. Infrastructure Repository (compiler-explorer/infra)
Contains `libraries.yaml` which defines:
- Library metadata
- Build instructions
- Version information

### 2. Main Repository (compiler-explorer/compiler-explorer)
Contains language-specific properties files:
- `c++.amazon.properties`
- `rust.amazon.properties`
- `fortran.amazon.properties`

## Library Addition Flow

```
1. User Input (language, library, version, optional type/package-install)
    ↓
2. Fork Creation/Detection
    ↓
3. Repository Cloning (to temp directory)
    ↓
4. Feature Branch Creation
    ├── add-{lang}-{lib}-{version}-infra
    └── add-{lang}-{lib}-{version}-main
    ↓
5. Enhanced Library Analysis (C/C++ only)
    ├── Check existing configuration (local/remote)
    ├── Clone and analyze target repository
    ├── Detect library type and CMake targets
    ├── Perform git tag lookup for version format
    └── Determine package installation requirements
    ↓
6. Language-Specific Processing
    ├── Build ce_install command with detected parameters
    ├── Run ce_install commands
    ├── Update libraries.yaml
    └── Update properties files
    ↓
7. Optional Verification (--verify flag)
    ├── Show diffs
    ├── Test installation (--install-test for C++)
    ├── Check library paths consistency
    └── Confirm with user
    ↓
8. Commit Changes
    ↓
9. Push to Fork
    ↓
10. Create Pull Requests
    └── Link related PRs
```

## ce_install Integration

The tool heavily relies on `ce_install` utilities from the infra repository:

### Setup Phase
```bash
cd infra_repo
make ce
```
This creates a Poetry environment with ce_install commands.

### Available Commands
- `ce_install add-crate` - Add Rust libraries
- `ce_install generate-rust-props` - Generate Rust properties
- `ce_install cpp-library add` - Add C++ libraries with various flags:
  - `--type` - Specify library type
  - `--static-lib-link` - Static library link targets
  - `--shared-lib-link` - Shared library link targets
  - `--package-install` - Enable CMake package installation
- `ce_install cpp-library generate-linux-props` - Generate Linux properties
- `ce_install cpp-library generate-windows-props` - Generate Windows properties
- `ce_install fortran-library add` - Add Fortran libraries
- `ce_install install` - Test library installation
- `ce_install list-paths` - Check library installation paths

## Error Handling Strategy

### Graceful Degradation
- Non-critical failures (like Windows props generation) show warnings but continue
- Critical failures (like library addition) stop the process

### User Feedback
- Clear error messages with suggested solutions
- Debug mode for detailed troubleshooting
- Progress indicators for long operations

## Temporary Directory Management

All operations happen in temporary directories:
```python
/tmp/ce-lib-wizard-{uuid}/
├── compiler-explorer/  # Main repo clone
└── infra/             # Infra repo clone
```

Benefits:
- No pollution of user's workspace
- Automatic cleanup on exit
- Isolation between runs

## Configuration Detection

### Library ID Generation
Converts GitHub URLs to valid identifiers:
- `https://github.com/fmtlib/fmt` → `fmt`
- `https://github.com/nlohmann/json` → `nlohmann_json`

### Interactive Configuration
For C/C++ libraries, the tool asks additional questions:
- Library type (if not auto-detected or overridden)
- Package installation requirement (for static/shared libraries)
- Note: packaged-headers automatically enables package installation

### Library Type Detection (C/C++)

#### Automatic Detection Logic
1. **Existing Configuration Check**: First checks if library already exists in libraries.yaml
   - Local check: If infra repo is available locally
   - Remote check: Temporarily clones infra repo to check configuration
   - Uses existing library type if found

2. **Repository Analysis**: Clones and analyzes the target repository
   - Has CMakeLists.txt → `packaged-headers` (default)
   - No CMakeLists.txt → `header-only`

3. **CMake Target Detection**: For static/shared libraries
   - Runs `cmake --build build --target help` to discover targets
   - Filters main targets (excludes test/doc/install targets)
   - Automatically populates staticliblink/sharedliblink fields

#### Supported Library Types
- `header-only`: Headers only, no compilation
- `packaged-headers`: Headers + CMake configuration (auto package_install)
- `static`: Static libraries with optional link targets
- `shared`: Shared libraries with optional link targets  
- `cshared`: C shared libraries

#### Version Format Detection
- Performs git tag lookup on remote repository using GitHub API for enhanced reliability
- Determines if library uses version prefix (e.g., 'v' in 'v1.2.3')
- Automatically normalizes user input (removes 'v' prefix) and sets target_prefix appropriately
- Validates all versions exist in the repository before proceeding
- Fails fast with clear error messages for non-existent versions
- Falls back to git ls-remote for non-GitHub repositories

## Performance Considerations

### Parallel Operations
Where possible, operations run in parallel:
- Dual repository cloning
- Multiple property file generation

### Caching
- Git credentials cached by Git/GitHub CLI
- Poetry environments cached between runs

## Security Model

### Fork-Based Workflow
- Users never push directly to upstream
- All changes go through user's fork
- PRs require upstream maintainer approval

### Authentication Security
- OAuth tokens never persisted
- CSRF protection on OAuth flow
- Tokens scoped to minimum required permissions

## Future Extensibility

The architecture supports:
- Additional language handlers
- New authentication methods
- API/service deployment
- Batch operations
- CI/CD integration
- Enhanced library type detection
- Automatic build configuration discovery
- Cross-language shared utilities

## Debug Mode Features

When `--debug` is enabled:
- Detailed command execution logs
- Git operation tracing
- ce_install output capture
- Environment variable inspection
- Full exception stack traces
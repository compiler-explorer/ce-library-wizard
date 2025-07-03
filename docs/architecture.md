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
- Detects library type (header-only vs packaged)
- Runs `ce_install cpp-library add`
- Generates Linux and Windows properties
- Validates library paths

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
1. User Input (language, library, version)
    ↓
2. Fork Creation/Detection
    ↓
3. Repository Cloning (to temp directory)
    ↓
4. Feature Branch Creation
    ├── add-{lang}-{lib}-{version}-infra
    └── add-{lang}-{lib}-{version}-main
    ↓
5. Language-Specific Processing
    ├── Run ce_install commands
    ├── Update libraries.yaml
    └── Update properties files
    ↓
6. Optional Verification (--verify flag)
    ├── Show diffs
    └── Confirm with user
    ↓
7. Commit Changes
    ↓
8. Push to Fork
    ↓
9. Create Pull Requests
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
- `ce_install cpp-library add` - Add C++ libraries
- `ce_install cpp-library generate-linux-props` - Generate Linux properties
- `ce_install fortran-library add` - Add Fortran libraries

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

### Library Type Detection (C++)
- Has CMakeLists.txt → `packaged-headers`
- No CMakeLists.txt → `header-only`

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

## Debug Mode Features

When `--debug` is enabled:
- Detailed command execution logs
- Git operation tracing
- ce_install output capture
- Environment variable inspection
- Full exception stack traces
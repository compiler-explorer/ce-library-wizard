# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

This project follows a strict separation of concerns pattern to support both CLI and AWS Lambda/REST API deployments:

### Directory Structure
```
/
├── core/           # Business logic - no external dependencies, pure functions
├── cli/            # CLI-specific implementation
├── api/            # REST API/Lambda handlers
├── shared/         # Shared utilities (logging, config, etc.)
└── tests/          # Unit tests (when needed)
```

### Development Principles

1. **Separation of Concerns**
   - Core business logic must be completely isolated from I/O operations
   - No direct network calls, file system access, or external dependencies in `core/`
   - CLI and API layers act as thin adapters that call core functions

2. **File Organization**
   - One module per file
   - Each function should have a single, clear responsibility
   - Group related functionality into subdirectories

3. **Function Design**
   - Pure functions in core logic (same input = same output)
   - Dependency injection for external services
   - Return structured data, not formatted strings

4. **Testing Strategy**
   - Write unit tests only when code doesn't require external connections
   - Focus tests on core business logic
   - Mock external dependencies when necessary

### Code Patterns

When implementing features:
1. Start with the core logic in `core/`
2. Create CLI wrapper in `cli/` that handles argument parsing and output formatting
3. Create API wrapper in `api/` that handles HTTP request/response
4. Both wrappers should call the same core functions

Example structure:
```
core/user.js         # User business logic
cli/user-cmd.js      # CLI command implementation
api/user-handler.js  # Lambda/API handler
```

### Implementation Guidelines

- Keep functions small and focused
- Use async/await for asynchronous operations
- Return errors as values, not exceptions (where appropriate)
- Validate input at the boundary (CLI/API layer)
- Process data in the core layer
- **Always place all imports at the top of the file** - avoid inline imports unless absolutely necessary for circular dependency resolution
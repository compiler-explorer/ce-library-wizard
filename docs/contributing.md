# Contributing to CE Library Wizard

Thank you for your interest in contributing to CE Library Wizard! This guide will help you get started.

## Development Setup

### Prerequisites
- Python 3.12 or higher
- Git
- Make
- GitHub CLI (optional but recommended)

### Setting Up Your Development Environment

1. **Fork and clone the repository**
   ```bash
   gh repo fork compiler-explorer/ce-lib-wizard --clone
   cd ce-lib-wizard
   ```

2. **Install dependencies**
   ```bash
   ./run.sh  # This will set up Poetry and install dependencies
   ```

3. **Verify installation**
   ```bash
   ./run.sh --help
   ```

## Code Style and Standards

### Code Formatting
We use Black and Ruff for code formatting and linting:

```bash
# Format code automatically
./run.sh --format

# Check formatting without changes
./run.sh --format --check
```

**Important:** Always run `./run.sh --format` before committing changes.

### Python Style Guide
- Follow PEP 8 with Black's formatting
- Use type hints for all function signatures
- Keep functions small and focused
- Write descriptive variable names

### Import Organization
- Place all imports at the top of files
- Group imports: standard library, third-party, local
- Avoid circular imports

Example:
```python
import logging
import tempfile
from pathlib import Path

import click
from pydantic import BaseModel

from core.models import LibraryConfig
from core.git_operations import GitManager
```

## Project Structure Guidelines

### Core Directory (`core/`)
- Pure business logic only
- No direct I/O operations
- No CLI-specific code
- All functions should be testable in isolation

### CLI Directory (`cli/`)
- User interaction code
- Argument parsing
- Output formatting
- Orchestration of core functions

## Making Changes

### 1. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

### 2. Make Your Changes
Follow the existing patterns:
- One module per file
- Clear function names
- Comprehensive error handling

### 3. Test Your Changes
Test manually with different scenarios:
```bash
# Test with debug mode
./run.sh --debug --verify --lang=rust --lib=test-crate --ver=0.1.0

# Test error handling
./run.sh --lang=cpp --lib=invalid-url --ver=1.0.0
```

### 4. Update Documentation
- Update README.md if adding new features
- Update relevant docs/ files
- Add docstrings to new functions

### 5. Commit Your Changes
Write clear commit messages:
```bash
git add .
git commit -m "Add support for X language libraries

- Implement XHandler class
- Add ce_install integration
- Update CLI to support --lang=x"
```

## Adding Support for New Languages

To add support for a new language:

1. **Create a handler class** in `core/{language}_handler.py`:
   ```python
   class NewLanguageHandler:
       def __init__(self, infra_path: Path, main_path: Path, debug: bool = False):
           self.infra_path = infra_path
           self.main_path = main_path
           self.debug = debug
       
       def add_library(self, config: LibraryConfig) -> str | None:
           # Implementation
           pass
   ```

2. **Update the Language enum** in `core/models.py`:
   ```python
   class Language(str, Enum):
       # ... existing languages ...
       NEW_LANGUAGE = "New Language"
   ```

3. **Add CLI support** in `cli/main.py`:
   - Update the `--lang` choices
   - Add a `process_{language}_library` function
   - Update the main dispatch logic

4. **Update documentation**:
   - Add to supported languages in README.md
   - Document any special requirements

## Common Development Tasks

### Running ce_install Commands Manually
```bash
cd /tmp/ce-lib-wizard-*/infra
poetry run ce_install --help
```

### Debugging Git Operations
```bash
export GIT_TRACE=1
./run.sh --debug ...
```

### Testing OAuth Flow
```bash
./run.sh --oauth --debug
# Check that browser opens and callback works
```

## Submitting Pull Requests

### PR Checklist
- [ ] Code is formatted with `./run.sh --format`
- [ ] Changes work with `--verify` flag
- [ ] Error cases are handled gracefully
- [ ] Documentation is updated
- [ ] Commit messages are clear
- [ ] PR description explains the changes

### PR Description Template
```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Documentation update

## Testing
How you tested the changes

## Additional Notes
Any additional context
```

## Reporting Issues

When reporting issues, please include:
1. The exact command you ran
2. The full error message
3. Debug output (`--debug` flag)
4. Your OS and Python version
5. Whether you're authenticated with GitHub

## Questions and Support

- Open an issue for bugs or feature requests
- Use discussions for questions
- Check existing issues before creating new ones

## Code of Conduct

- Be respectful and inclusive
- Welcome newcomers
- Focus on constructive feedback
- Follow the project's goals

## Development Tips

### Understanding ce_install
The `ce_install` tool is the heart of library management. Familiarize yourself with:
```bash
# See available commands
cd infra && poetry run ce_install --help

# Test commands manually
poetry run ce_install list
```

### Debugging Authentication
```python
# Add debug prints in github_auth.py
logger.debug(f"Token type: {type(token)}")
logger.debug(f"Token length: {len(token) if token else 0}")
```

### Testing Error Scenarios
- Test with invalid GitHub URLs
- Test with private repositories
- Test without authentication
- Test with existing library versions

Thank you for contributing to CE Library Wizard!
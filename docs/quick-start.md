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

### Test Installation (C++ only)
Validate that the library installs correctly:
```bash
./run.sh --install-test --lang=cpp --lib=https://github.com/fmtlib/fmt --ver=10.2.1
```

### Keep Temporary Files
For debugging, keep the temporary directories after the tool exits:
```bash
./run.sh --keep-temp --lang=rust --lib=serde --ver=1.0.195
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
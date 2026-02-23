# CE Library Wizard

A CLI tool that automates the process of adding libraries to [Compiler Explorer](https://compiler-explorer.com/).

## Quick Start

```bash
# Clone and run
git clone https://github.com/compiler-explorer/ce-library-wizard.git
cd ce-library-wizard
./run.sh
```

See the [Quick Start Guide](docs/quick-start.md) for more examples.

## Features

- 🚀 Interactive CLI for adding libraries to Compiler Explorer
- 🦀 **Rust** - Fully automated with crate support + bulk top 100 crates
- ⚔️ **C** - Shared/static library support  
- ⚡ **C++** - Smart library type detection
- 🔧 **Fortran** - FPM package integration
- 🔢 **Multi-version** - Add multiple versions in one command
- 🔐 Multiple authentication methods
- 🍴 Automatic GitHub fork management
- 📝 Preview changes before committing

## Prerequisites

- **Python 3.12+**
- **Git** - [Installation guide](https://git-scm.com/downloads)
- **GitHub CLI** (recommended) - [Installation guide](https://cli.github.com/)
- **Make**

Set up GitHub CLI:
```bash
gh auth login
```

## Basic Usage

```bash
# Interactive mode
./run.sh

# Add a Rust library
./run.sh --lang=rust --lib=serde --ver=1.0.195

# Add a C++ library with automatic type detection
./run.sh --lang=c++ --lib=https://github.com/fmtlib/fmt --ver=10.2.1

# Add a header-only C++ library
./run.sh --lang=c++ --lib=https://github.com/bobluppes/graaf --ver=v1.1.1 --type=header-only

# Preview changes first
./run.sh --verify --lang=rust --lib=tokio --ver=1.35.0
```

## Documentation

- 📚 [Quick Start Guide](docs/quick-start.md) - Get started in minutes
- 🔧 [Language Support](docs/languages.md) - Language-specific details
- ❓ [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- 🏗️ [Architecture](docs/architecture.md) - How it works internally
- 🚀 [Advanced Usage](docs/advanced-usage.md) - Automation and customization
- 🤝 [Contributing](docs/contributing.md) - Development guide

## How it Works

CE Library Wizard automates the complex process of adding libraries to Compiler Explorer by:

1. Managing GitHub forks and branches automatically
2. Running language-specific `ce_install` commands
3. Updating configuration files in both required repositories
4. Creating linked pull requests

See [Architecture Documentation](docs/architecture.md) for details.

## Contributing

Contributions are welcome! See our [Contributing Guide](docs/contributing.md).

## License

MIT

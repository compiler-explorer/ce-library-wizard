# CE Library Wizard Documentation

This directory contains detailed documentation for CE Library Wizard.

## Getting Started

- **[Quick Start Guide](quick-start.md)** - Get up and running in minutes
- **[Language Support](languages.md)** - Detailed information for each supported language

## Reference

- **[Troubleshooting Guide](troubleshooting.md)** - Solutions to common problems and error messages
- **[Architecture & Internals](architecture.md)** - Technical details about how the tool works
- **[Advanced Usage](advanced-usage.md)** - Advanced features, automation, and customization

## Development

- **[Contributing Guide](contributing.md)** - Guidelines for contributing to the project

## Quick Links

- [Main README](../README.md) - Project overview
- [GitHub Issues](https://github.com/compiler-explorer/ce-lib-wizard/issues) - Report bugs or request features
- [Compiler Explorer](https://compiler-explorer.com) - The main Compiler Explorer website

## Overview

CE Library Wizard automates the process of adding libraries to Compiler Explorer by:
1. Managing GitHub forks and branches
2. Running the appropriate `ce_install` commands
3. Updating configuration files in both repositories
4. Creating pull requests with proper linking

The tool supports multiple languages (Rust, C++, Fortran) with language-specific handling for each.
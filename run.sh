#!/usr/bin/env bash

# CE Library Wizard runner script
# This script sets up Poetry and runs the CLI
#
# Environment variables:
#   DEBUG=1 or CE_DEBUG=1  - Enable verbose output including Poetry installation details

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    print_error "python3 is not installed. Please install Python 3.12 or higher."
    exit 1
fi

# Get Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_info "Found Python $PYTHON_VERSION"

# Check Python version is 3.12+
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    print_error "Python 3.12 or higher is required. Found Python $PYTHON_VERSION"
    exit 1
fi

# Set up directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Always cleanup existing environment to ensure fresh install
if [ -d ".venv" ]; then
    print_info "Cleaning up existing virtual environment..."
    rm -rf .venv
fi

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    print_info "Poetry not found. Installing Poetry..."
    
    # Install Poetry
    curl -sSL https://install.python-poetry.org | python3 -
    
    # Add Poetry to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    
    # Check again
    if ! command -v poetry &> /dev/null; then
        print_error "Failed to install Poetry"
        print_info "Please install Poetry manually: https://python-poetry.org/docs/#installation"
        exit 1
    fi
    
    print_info "Poetry installed successfully!"
fi

# Configure Poetry to create virtual environment in project directory
poetry config virtualenvs.in-project true --local 2>/dev/null || true

# Install dependencies
print_info "Installing dependencies with Poetry..."
if [[ "${DEBUG:-}" == "1" || "${CE_DEBUG:-}" == "1" ]]; then
    poetry install --no-interaction --no-ansi
else
    poetry install --no-interaction --no-ansi --quiet
fi

if [ $? -eq 0 ]; then
    print_info "Installation complete!"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Check if GitHub authentication is available
if [ -z "$GITHUB_TOKEN" ] && ! command -v gh &> /dev/null; then
    print_warning "No GitHub authentication found."
    print_info "To enable PR creation, use one of these options:"
    print_info "  - Install and authenticate GitHub CLI: gh auth login"
    print_info "  - Set GITHUB_TOKEN environment variable"
    print_info "  - Use --oauth flag for browser-based authentication"
    echo
elif [ -z "$GITHUB_TOKEN" ] && ! gh auth status &> /dev/null; then
    print_warning "GitHub CLI is installed but not authenticated."
    print_info "To enable PR creation, run: gh auth login"
    echo
fi

# Check for special commands
if [ "$1" = "--format" ]; then
    if [ "$2" = "--check" ]; then
        print_info "Running code quality checks..."
        echo "======================================"
        echo
        
        print_info "Running black formatter check..."
        if ! poetry run black --check --diff .; then
            print_error "Black formatting check failed!"
            exit 1
        fi
        
        print_info "Running ruff linter check..."
        if ! poetry run ruff check .; then
            print_error "Ruff linting check failed!"
            exit 1
        fi
        
        print_info "Running pytype type checking..."
        if poetry run pytype; then
            print_info "PyType type checking passed!"
        else
            print_warning "PyType type checking completed with warnings (not failing build)"
        fi
        
        print_info "All code quality checks passed!"
        exit 0
    else
        print_info "Running code formatters..."
        echo "======================================"
        echo
        
        print_info "Running black formatter..."
        poetry run black .
        
        print_info "Running ruff formatter..."
        poetry run ruff check --fix .
        
        print_info "Formatting complete!"
        exit 0
    fi
fi

# Run the CLI
print_info "Starting CE Library Wizard..."
echo "======================================"
echo

# Pass all arguments to the CLI using Poetry
exec poetry run ce-lib-wizard "$@"
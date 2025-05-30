#!/usr/bin/env bash

# CE Library Wizard runner script
# This script sets up Poetry and runs the CLI

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
poetry install --no-interaction --no-ansi

if [ $? -eq 0 ]; then
    print_info "Installation complete!"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Check if GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    print_warning "GITHUB_TOKEN not set. You won't be able to create pull requests."
    print_info "To enable PR creation, run: export GITHUB_TOKEN=your_token_here"
    echo
fi

# Run the CLI
print_info "Starting CE Library Wizard..."
echo "======================================"
echo

# Pass all arguments to the CLI using Poetry
exec poetry run ce-lib-wizard "$@"
#!/usr/bin/env bash

# CE Library Wizard runner script
# This script sets up a local Python environment and runs the CLI

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
    print_error "python3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Get Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
print_info "Found Python $PYTHON_VERSION"

# Check Python version is 3.8+
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
    print_error "Python 3.8 or higher is required. Found Python $PYTHON_VERSION"
    exit 1
fi

# Set up virtual environment directory
VENV_DIR=".venv"
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Remove existing venv to ensure clean state
rm -rf "$VENV_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    
    if [ $? -ne 0 ]; then
        print_error "Failed to create virtual environment"
        print_info "Trying to install python3-venv..."
        
        # Try to provide platform-specific instructions
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            print_info "On Ubuntu/Debian, try: sudo apt-get install python3-venv"
            print_info "On RHEL/CentOS/Fedora, try: sudo yum install python3-venv"
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            print_info "On macOS, venv should be included with Python. Try reinstalling Python via Homebrew: brew reinstall python3"
        fi
        exit 1
    fi
fi

# Activate virtual environment
print_info "Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
print_info "Ensuring pip is up to date..."
python3 -m pip install --upgrade pip >/dev/null 2>&1

# Install/upgrade the package
if [ ! -f "$VENV_DIR/.installed" ] || [ requirements.txt -nt "$VENV_DIR/.installed" ]; then
    print_info "Installing dependencies..."
    pip install -e .
    
    if [ $? -eq 0 ]; then
        touch "$VENV_DIR/.installed"
        print_info "Installation complete!"
    else
        print_error "Failed to install dependencies"
        exit 1
    fi
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

# Pass all arguments to the CLI
exec python3 -m cli.main "$@"
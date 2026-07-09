#!/bin/bash
# build-all.sh - Build all virtual device drivers and tools
# 
# This script builds all kernel modules, tools, and examples
# for the Intel NUC Virtual Device Platform.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${BUILD_DIR}/logs"
BUILD_LOG="${LOG_DIR}/build_$(date +%Y%m%d_%H%M%S).log"
DRIVERS_DIR="${BUILD_DIR}/drivers"
TOOLS_DIR="${BUILD_DIR}/tools"
EXAMPLES_DIR="${BUILD_DIR}/examples"

# Create log directory
mkdir -p "$LOG_DIR"

# Function to log messages
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "$msg" | tee -a "$BUILD_LOG"
}

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo -e "$message" >> "$BUILD_LOG"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_status "$RED" "✗ Please run as root"
        exit 1
    fi
}

# Function to check dependencies
check_dependencies() {
    log "Checking dependencies..."
    
    local deps=(
        "make"
        "gcc"
        "git"
        "python3"
        "python3-pip"
        "linux-headers-$(uname -r)"
        "dkms"
        "build-essential"
    )
    
    local missing=()
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            if ! dpkg -l | grep -q "$dep"; then
                missing+=("$dep")
            fi
        fi
    done
    
    if [ ${#missing[@]} -ne 0 ]; then
        print_status "$YELLOW" "⚠ Missing dependencies: ${missing[*]}"
        echo "Installing missing dependencies..."
        apt-get update
        apt-get install -y "${missing[@]}"
    fi
    
    print_status "$GREEN" "✓ All dependencies satisfied"
}

# Function to build kernel modules
build_modules() {
    log "Building kernel modules..."
    
    cd "$DRIVERS_DIR"
    
    # Build all modules
    for dir in virtual-*/; do
        if [ -d "$dir" ]; then
            print_status "$BLUE" "→ Building $dir..."
            cd "$dir"
            
            # Clean first
            make clean >> "$BUILD_LOG" 2>&1
            
            # Build
            if make all >> "$BUILD_LOG" 2>&1; then
                print_status "$GREEN" "  ✓ $dir built successfully"
            else
                print_status "$RED" "  ✗ Failed to build $dir"
                tail -20 "$BUILD_LOG"
                return 1
            fi
            
            cd ..
        fi
    done
    
    print_status "$GREEN" "✓ All kernel modules built"
}

# Function to build tools
build_tools() {
    log "Building tools..."
    
    cd "$TOOLS_DIR"
    
    # Make Python tools executable
    for tool in *.py; do
        if [ -f "$tool" ]; then
            chmod +x "$tool"
            print_status "$GREEN" "  ✓ Made $tool executable"
        fi
    done
    
    # Build any C tools
    for tool in *.c; do
        if [ -f "$tool" ]; then
            local name="${tool%.c}"
            print_status "$BLUE" "  → Building $tool..."
            gcc -o "$name" "$tool" -Wall -Wextra -O2
            if [ $? -eq 0 ]; then
                print_status "$GREEN" "    ✓ $tool built successfully"
            else
                print_status "$RED" "    ✗ Failed to build $tool"
            fi
        fi
    done
    
    print_status "$GREEN" "✓ Tools built"
}

# Function to build examples
build_examples() {
    log "Building examples..."
    
    cd "$EXAMPLES_DIR"
    
    # Build C examples
    for example in $(find . -name "*.c"); do
        local dir=$(dirname "$example")
        local name=$(basename "$example" .c)
        
        print_status "$BLUE" "→ Building $example..."
        cd "$dir"
        
        gcc -o "$name" "$name.c" -Wall -Wextra -O2
        
        if [ $? -eq 0 ]; then
            print_status "$GREEN" "  ✓ $name built successfully"
        else
            print_status "$RED" "  ✗ Failed to build $name"
        fi
        
        cd - > /dev/null
    done
    
    # Make shell scripts executable
    for script in $(find . -name "*.sh"); do
        chmod +x "$script"
        print_status "$GREEN" "  ✓ Made $script executable"
    done
    
    # Make Python examples executable
    for script in $(find . -name "*.py"); do
        chmod +x "$script"
        print_status "$GREEN" "  ✓ Made $script executable"
    done
    
    print_status "$GREEN" "✓ Examples built"
}

# Function to install modules
install_modules() {
    log "Installing kernel modules..."
    
    cd "$DRIVERS_DIR"
    
    for dir in virtual-*/; do
        if [ -d "$dir" ]; then
            print_status "$BLUE" "→ Installing $dir..."
            cd "$dir"
            
            if make install >> "$BUILD_LOG" 2>&1; then
                print_status "$GREEN" "  ✓ $dir installed"
            else
                print_status "$RED" "  ✗ Failed to install $dir"
            fi
            
            cd ..
        fi
    done
    
    # Update module dependencies
    depmod -a
    
    print_status "$GREEN" "✓ Modules installed"
}

# Function to setup Python environment
setup_python() {
    log "Setting up Python environment..."
    
    cd "$BUILD_DIR"
    
    if [ -f "requirements.txt" ]; then
        pip3 install -r requirements.txt >> "$BUILD_LOG" 2>&1
        if [ $? -eq 0 ]; then
            print_status "$GREEN" "✓ Python dependencies installed"
        else
            print_status "$YELLOW" "⚠ Failed to install Python dependencies"
        fi
    fi
    
    # Install tools in development mode
    if [ -f "setup.py" ]; then
        python3 setup.py develop >> "$BUILD_LOG" 2>&1
        if [ $? -eq 0 ]; then
            print_status "$GREEN" "✓ Tools installed in development mode"
        fi
    fi
}

# Function to create documentation
build_docs() {
    log "Building documentation..."
    
    cd "$BUILD_DIR"
    
    if [ -d "docs" ]; then
        # Check if Sphinx is installed
        if command -v sphinx-build &> /dev/null; then
            sphinx-build -b html docs/ docs/_build/html >> "$BUILD_LOG" 2>&1
            if [ $? -eq 0 ]; then
                print_status "$GREEN" "✓ Documentation built"
            else
                print_status "$YELLOW" "⚠ Failed to build documentation"
            fi
        else
            print_status "$YELLOW" "⚠ Sphinx not installed, skipping documentation"
        fi
    fi
}

# Function to run tests
run_tests() {
    log "Running tests..."
    
    cd "$BUILD_DIR"
    
    if [ -f "scripts/test-all.sh" ]; then
        ./scripts/test-all.sh >> "$BUILD_LOG" 2>&1
        if [ $? -eq 0 ]; then
            print_status "$GREEN" "✓ All tests passed"
        else
            print_status "$RED" "✗ Some tests failed"
        fi
    else
        print_status "$YELLOW" "⚠ No test script found"
    fi
}

# Function to show build status
show_status() {
    log "Build Status:"
    echo ""
    
    # Show built modules
    print_status "$CYAN" "Built Modules:"
    for module in $(find "$DRIVERS_DIR" -name "*.ko" -type f); do
        local name=$(basename "$module")
        local size=$(du -h "$module" | cut -f1)
        echo "  ✓ $name ($size)"
    done
    
    echo ""
    
    # Show built tools
    print_status "$CYAN" "Built Tools:"
    for tool in $(find "$TOOLS_DIR" -maxdepth 1 -type f -executable); do
        echo "  ✓ $(basename "$tool")"
    done
    
    echo ""
    
    # Show built examples
    print_status "$CYAN" "Built Examples:"
    for example in $(find "$EXAMPLES_DIR" -type f -executable); do
        echo "  ✓ $(basename "$example")"
    done
    
    echo ""
    
    # Show log file
    print_status "$CYAN" "Build Log: $BUILD_LOG"
}

# Function to cleanup
cleanup() {
    log "Cleaning up build artifacts..."
    
    cd "$DRIVERS_DIR"
    
    for dir in virtual-*/; do
        if [ -d "$dir" ]; then
            print_status "$BLUE" "→ Cleaning $dir..."
            cd "$dir"
            make clean >> "$BUILD_LOG" 2>&1
            cd ..
        fi
    done
    
    # Remove Python cache
    find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    find "$BUILD_DIR" -type f -name "*.pyc" -delete 2>/dev/null
    
    print_status "$GREEN" "✓ Cleanup complete"
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Build Script for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-c, --clean${NC}     Clean build artifacts before building
  ${GREEN}-t, --test${NC}      Run tests after building
  ${GREEN}-d, --doc${NC}       Build documentation
  ${GREEN}-i, --install${NC}   Install modules after building
  ${GREEN}-v, --verbose${NC}   Enable verbose output
  ${GREEN}-j, --jobs${NC} N    Number of parallel jobs (default: $(nproc))

Examples:
  # Build everything
  $0
  
  # Clean and build
  $0 --clean
  
  # Build and install
  $0 --install
  
  # Build with tests and documentation
  $0 --test --doc

EOF
}

# Main function
main() {
    # Parse arguments
    CLEAN=false
    RUN_TESTS=false
    BUILD_DOCS=false
    INSTALL=false
    VERBOSE=false
    JOBS=$(nproc)
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -c|--clean)
                CLEAN=true
                shift
                ;;
            -t|--test)
                RUN_TESTS=true
                shift
                ;;
            -d|--doc)
                BUILD_DOCS=true
                shift
                ;;
            -i|--install)
                INSTALL=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -j|--jobs)
                JOBS="$2"
                shift 2
                ;;
            *)
                print_status "$RED" "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Set verbose mode
    if [ "$VERBOSE" = true ]; then
        set -x
    fi
    
    # Start build
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Intel NUC Virtual Device Platform Build"
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Build Started: $(date)"
    print_status "$CYAN" "Log File: $BUILD_LOG"
    print_status "$CYAN" "========================================="
    echo ""
    
    # Check root
    check_root
    
    # Clean if requested
    if [ "$CLEAN" = true ]; then
        cleanup
        echo ""
    fi
    
    # Build everything
    check_dependencies
    echo ""
    
    setup_python
    echo ""
    
    build_modules
    echo ""
    
    build_tools
    echo ""
    
    build_examples
    echo ""
    
    if [ "$BUILD_DOCS" = true ]; then
        build_docs
        echo ""
    fi
    
    if [ "$INSTALL" = true ]; then
        install_modules
        echo ""
    fi
    
    if [ "$RUN_TESTS" = true ]; then
        run_tests
        echo ""
    fi
    
    # Show status
    show_status
    
    print_status "$CYAN" "========================================="
    print_status "$GREEN" "✓ Build completed successfully"
    print_status "$CYAN" "Build Finished: $(date)"
    print_status "$CYAN" "========================================="
}

# Trap signals
trap 'print_status "$RED" "Build interrupted"; exit 1' INT TERM

# Execute main
main "$@"

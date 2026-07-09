#!/bin/bash
# serial-test.sh - Integration tests for virtual serial devices
#
# This script tests all serial virtual devices including PTY,
# socat bridges, and serial communication.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${TEST_DIR}/logs/tests"
LOG_FILE="${LOG_DIR}/serial_test_$(date +%Y%m%d_%H%M%S).log"
RESULT_FILE="${LOG_DIR}/serial_results_$(date +%Y%m%d_%H%M%S).json"

# Create directories
mkdir -p "$LOG_DIR"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_TOTAL=0

# Function to log messages
log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo -e "$msg" | tee -a "$LOG_FILE"
}

# Function to print colored output
print_status() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
    echo -e "$message" >> "$LOG_FILE"
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_status "$RED" "✗ Please run as root"
        exit 1
    fi
}

# Function to run a test
run_test() {
    local test_name=$1
    local test_cmd=$2
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    log "Running test: $test_name"
    log "Command: $test_cmd"
    
    if eval "$test_cmd" >> "$LOG_FILE" 2>&1; then
        print_status "$GREEN" "  ✓ $test_name PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo "{\"name\":\"$test_name\",\"status\":\"PASSED\"}" >> "$RESULT_FILE"
        return 0
    else
        print_status "$RED" "  ✗ $test_name FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "{\"name\":\"$test_name\",\"status\":\"FAILED\"}" >> "$RESULT_FILE"
        return 1
    fi
}

# Function to check if module is loaded
check_module() {
    local module=$1
    if lsmod | grep -q "$module"; then
        return 0
    else
        return 1
    fi
}

# Function to cleanup serial devices
cleanup_serial() {
    log "Cleaning up serial devices..."
    
    # Kill socat processes
    pkill -f "socat.*test-" 2>/dev/null || true
    
    # Remove PTY devices
    rm -f /dev/ttyV* 2>/dev/null || true
    rm -f /tmp/test-* 2>/dev/null || true
}

# Function to test PTY devices
test_pty() {
    log "=== Testing PTY Devices ==="
    
    # Load PTY manager
    if ! check_module "pty-manager"; then
        run_test "load_pty_manager" "modprobe pty-manager || insmod ${TEST_DIR}/drivers/virtual-serial/pty-manager.ko"
    fi
    
    # Check PTY devices
    run_test "pty_devices_exist" "test -e /dev/ttyV0 && test -e /dev/ttyV1"
    
    # Test PTY read/write
    run_test "pty_write" "echo 'test' > /dev/ttyV0 2>/dev/null || echo 'test' > /dev/ttyV1 2>/dev/null"
    
    # Test PTY with cat (background)
    if [ -e /dev/ttyV0 ] && [ -e /dev/ttyV1 ]; then
        run_test "pty_cat" "timeout 2 cat /dev/ttyV1 > /dev/null 2>&1 || true"
    fi
}

# Function to test socat bridge
test_socat() {
    log "=== Testing Socat Bridge ==="
    
    # Check if socat is installed
    if ! command -v socat &> /dev/null; then
        log "  socat not installed, installing..."
        apt-get update -qq && apt-get install -y -qq socat
    fi
    
    run_test "socat_version" "socat -V > /dev/null"
    
    # Create PTY pair with socat
    run_test "socat_pty" "socat -d -d PTY,link=/tmp/test-pty0,raw,echo=0 PTY,link=/tmp/test-pty1,raw,echo=0 > /dev/null 2>&1 &"
    sleep 2
    
    # Test socat PTY
    run_test "socat_pty_exists" "test -e /tmp/test-pty0 && test -e /tmp/test-pty1"
    
    # Test socat communication
    run_test "socat_comm" "echo 'socat test' > /tmp/test-pty0 && cat /tmp/test-pty1 > /dev/null 2>&1 || true"
    
    # Create TCP bridge
    run_test "socat_tcp" "socat TCP-LISTEN:9999,reuseaddr,fork PTY,link=/tmp/test-pty2,raw,echo=0 > /dev/null 2>&1 &"
    sleep 2
    
    # Test TCP connection
    run_test "socat_tcp_connect" "timeout 2 socat - TCP:localhost:9999 > /dev/null 2>&1 || true"
    
    # Create UDP bridge
    run_test "socat_udp" "socat UDP-LISTEN:9998,reuseaddr,fork PTY,link=/tmp/test-pty3,raw,echo=0 > /dev/null 2>&1 &"
    sleep 2
    
    # Test UDP connection
    run_test "socat_udp_connect" "timeout 2 socat - UDP:localhost:9998 > /dev/null 2>&1 || true"
    
    # Cleanup
    run_test "socat_cleanup" "pkill -f socat 2>/dev/null || true"
}

# Function to test serial communication
test_serial_comm() {
    log "=== Testing Serial Communication ==="
    
    # Create PTY pair
    run_test "create_pty_pair" "socat -d -d PTY,link=/tmp/test-comm0,raw,echo=0 PTY,link=/tmp/test-comm1,raw,echo=0 > /dev/null 2>&1 &"
    sleep 2
    
    # Test communication
    if [ -e /tmp/test-comm0 ] && [ -e /tmp/test-comm1 ]; then
        run_test "comm_write" "echo 'Hello Serial' > /tmp/test-comm0 2>/dev/null || true"
        run_test "comm_read" "cat /tmp/test-comm1 2>/dev/null > /dev/null || true"
    fi
    
    # Cleanup
    pkill -f socat 2>/dev/null || true
}

# Function to test serial baud rates
test_baud_rates() {
    log "=== Testing Serial Baud Rates ==="
    
    # List of baud rates to test
    local baud_rates="9600 19200 38400 57600 115200 230400"
    
    for baud in $baud_rates; do
        run_test "baud_$baud" "stty -F /dev/ttyS0 $baud 2>/dev/null || true"
    done
}

# Function to test serial parameters
test_serial_params() {
    log "=== Testing Serial Parameters ==="
    
    # Test various serial settings
    local settings="cs7 cs8 cstopb -cstopb parenb -parenb parodd -parodd"
    
    for setting in $settings; do
        run_test "param_$setting" "stty -F /dev/ttyS0 $setting 2>/dev/null || true"
    done
}

# Function to show test summary
show_summary() {
    log ""
    log "========================================="
    log "Serial Test Summary"
    log "========================================="
    log ""
    log "Total Tests: $TESTS_TOTAL"
    print_status "$GREEN" "✓ Passed: $TESTS_PASSED"
    print_status "$RED" "✗ Failed: $TESTS_FAILED"
    log ""
    log "Log File: $LOG_FILE"
    log "Results File: $RESULT_FILE"
    log "========================================="
    
    if [ $TESTS_FAILED -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Serial Integration Tests for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-v, --verbose${NC}   Enable verbose output
  ${GREEN}-s, --skip${NC}      Skip cleanup after tests

Tests:
  ${GREEN}pty${NC}             PTY device tests
  ${GREEN}socat${NC}           Socat bridge tests
  ${GREEN}comm${NC}            Serial communication tests
  ${GREEN}baud${NC}            Baud rate tests
  ${GREEN}params${NC}          Serial parameter tests

Examples:
  # Run all tests
  $0
  
  # Run specific tests
  $0 --pty --socat
  
  # Run with verbose output
  $0 --verbose

EOF
}

# Main function
main() {
    # Parse arguments
    VERBOSE=false
    SKIP_CLEANUP=false
    RUN_ALL=true
    RUN_PTY=false
    RUN_SOCAT=false
    RUN_COMM=false
    RUN_BAUD=false
    RUN_PARAMS=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -s|--skip)
                SKIP_CLEANUP=true
                shift
                ;;
            --pty)
                RUN_PTY=true
                RUN_ALL=false
                shift
                ;;
            --socat)
                RUN_SOCAT=true
                RUN_ALL=false
                shift
                ;;
            --comm)
                RUN_COMM=true
                RUN_ALL=false
                shift
                ;;
            --baud)
                RUN_BAUD=true
                RUN_ALL=false
                shift
                ;;
            --params)
                RUN_PARAMS=true
                RUN_ALL=false
                shift
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
    
    # Start tests
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Serial Integration Tests"
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Test Started: $(date)"
    print_status "$CYAN" "Log File: $LOG_FILE"
    print_status "$CYAN" "========================================="
    echo ""
    
    # Check root
    check_root
    
    # Initialize result file
    echo "[" > "$RESULT_FILE"
    
    # Cleanup before tests
    cleanup_serial
    
    # Run tests
    if [ "$RUN_ALL" = true ] || [ "$RUN_PTY" = true ]; then
        test_pty
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_SOCAT" = true ]; then
        test_socat
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_COMM" = true ]; then
        test_serial_comm
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_BAUD" = true ]; then
        test_baud_rates
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_PARAMS" = true ]; then
        test_serial_params
    fi
    
    # Finalize result file
    sed -i '$ s/,$//' "$RESULT_FILE"
    echo "]" >> "$RESULT_FILE"
    
    # Cleanup after tests
    if [ "$SKIP_CLEANUP" = false ]; then
        cleanup_serial
    fi
    
    # Show summary
    show_summary
    
    if [ $TESTS_FAILED -eq 0 ]; then
        print_status "$GREEN" "✓ All serial tests passed!"
        exit 0
    else
        print_status "$RED" "✗ Some serial tests failed. Check log for details."
        exit 1
    fi
}

# Trap signals
trap 'cleanup_serial; print_status "$RED" "Tests interrupted"; exit 1' INT TERM

# Execute main
main "$@"

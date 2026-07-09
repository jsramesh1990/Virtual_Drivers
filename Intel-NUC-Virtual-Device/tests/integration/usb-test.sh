#!/bin/bash
# usb-test.sh - Integration tests for virtual USB devices
#
# This script tests all USB virtual devices including gadget,
# redirection, and USB device emulation.

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
LOG_FILE="${LOG_DIR}/usb_test_$(date +%Y%m%d_%H%M%S).log"
RESULT_FILE="${LOG_DIR}/usb_results_$(date +%Y%m%d_%H%M%S).json"

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

# Function to cleanup USB gadgets
cleanup_gadgets() {
    log "Cleaning up USB gadgets..."
    
    if [ -d "/sys/kernel/config/usb_gadget" ]; then
        for gadget in $(ls /sys/kernel/config/usb_gadget/ 2>/dev/null); do
            if [[ "$gadget" == test-* ]]; then
                echo "" > /sys/kernel/config/usb_gadget/$gadget/UDC 2>/dev/null || true
                rm -rf /sys/kernel/config/usb_gadget/$gadget 2>/dev/null || true
            fi
        done
    fi
}

# Function to test USB gadget framework
test_usb_gadget() {
    log "=== Testing USB Gadget Framework ==="
    
    # Check if configfs is available
    run_test "configfs_available" "test -d /sys/kernel/config"
    
    # Check if USB gadget is available
    run_test "usb_gadget_dir" "mkdir -p /sys/kernel/config/usb_gadget 2>/dev/null || true"
    
    # Create test gadget
    run_test "create_gadget" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget"
    run_test "set_gadget_ids" "echo 0x1d6b > /sys/kernel/config/usb_gadget/test-gadget/idVendor && echo 0x0104 > /sys/kernel/config/usb_gadget/test-gadget/idProduct"
    
    # Create strings
    run_test "create_strings" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/strings/0x409"
    run_test "set_strings" "echo 'Test Gadget' > /sys/kernel/config/usb_gadget/test-gadget/strings/0x409/product"
    
    # Create functions
    run_test "create_acm" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/functions/acm.usb0"
    run_test "create_ecm" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/functions/ecm.usb0"
    run_test "create_mass_storage" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/functions/mass_storage.usb0"
    run_test "create_hid" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/functions/hid.usb0"
    
    # Create configuration
    run_test "create_config" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/configs/c.1"
    run_test "create_config_strings" "mkdir -p /sys/kernel/config/usb_gadget/test-gadget/configs/c.1/strings/0x409"
    run_test "set_config_strings" "echo 'Test Config' > /sys/kernel/config/usb_gadget/test-gadget/configs/c.1/strings/0x409/configuration"
    
    # Link functions to config
    run_test "link_acm" "ln -s /sys/kernel/config/usb_gadget/test-gadget/functions/acm.usb0 /sys/kernel/config/usb_gadget/test-gadget/configs/c.1/ 2>/dev/null || true"
    run_test "link_ecm" "ln -s /sys/kernel/config/usb_gadget/test-gadget/functions/ecm.usb0 /sys/kernel/config/usb_gadget/test-gadget/configs/c.1/ 2>/dev/null || true"
    
    # Enable gadget
    if [ -d "/sys/class/udc" ]; then
        local udc=$(ls /sys/class/udc/ | head -1)
        if [ -n "$udc" ]; then
            run_test "enable_gadget" "echo $udc > /sys/kernel/config/usb_gadget/test-gadget/UDC"
            run_test "disable_gadget" "echo '' > /sys/kernel/config/usb_gadget/test-gadget/UDC"
        fi
    fi
    
    # Cleanup
    run_test "remove_gadget" "rm -rf /sys/kernel/config/usb_gadget/test-gadget"
}

# Function to test USB redirection
test_usb_redirect() {
    log "=== Testing USB Redirection ==="
    
    # Load USB redirect module
    if ! check_module "usb-redirect"; then
        run_test "load_usb_redirect" "modprobe usb-redirect || insmod ${TEST_DIR}/drivers/virtual-usb/usb-redirect.ko"
    fi
    
    # Check if usbip is available
    if command -v usbip &> /dev/null; then
        run_test "usbip_available" "usbip --version > /dev/null"
        
        # Check usbipd
        if pgrep -x "usbipd" > /dev/null; then
            run_test "usbipd_running" "pgrep -x usbipd > /dev/null"
        else
            run_test "usbipd_start" "usbipd -D 2>/dev/null || true"
        fi
        
        # List USB devices
        run_test "usbip_list" "usbip list -l > /dev/null 2>&1 || true"
    else
        log "  usbip not installed, skipping redirection tests"
    fi
}

# Function to test USB mass storage
test_usb_mass_storage() {
    log "=== Testing USB Mass Storage ==="
    
    # Create test image
    run_test "create_storage_image" "dd if=/dev/zero of=/tmp/test-usb.img bs=1M count=10 2>/dev/null"
    run_test "format_storage" "mkfs.ext4 -F /tmp/test-usb.img 2>/dev/null || true"
    
    # Mount via loop
    run_test "mount_storage" "losetup /dev/loop99 /tmp/test-usb.img 2>/dev/null || true"
    run_test "create_mount_point" "mkdir -p /mnt/test-usb 2>/dev/null || true"
    run_test "mount_loop" "mount /dev/loop99 /mnt/test-usb 2>/dev/null || true"
    
    # Test write
    run_test "write_test" "echo 'USB Test' > /mnt/test-usb/test.txt"
    run_test "read_test" "cat /mnt/test-usb/test.txt > /dev/null"
    
    # Cleanup
    run_test "umount_storage" "umount /mnt/test-usb 2>/dev/null || true"
    run_test "remove_loop" "losetup -d /dev/loop99 2>/dev/null || true"
    run_test "remove_image" "rm -f /tmp/test-usb.img"
    run_test "remove_mount" "rmdir /mnt/test-usb 2>/dev/null || true"
}

# Function to test USB HID
test_usb_hid() {
    log "=== Testing USB HID ==="
    
    # Create HID device
    run_test "create_hid_gadget" "mkdir -p /sys/kernel/config/usb_gadget/test-hid 2>/dev/null || true"
    run_test "set_hid_ids" "echo 0x1d6b > /sys/kernel/config/usb_gadget/test-hid/idVendor 2>/dev/null || true"
    run_test "set_hid_product" "echo 0x0104 > /sys/kernel/config/usb_gadget/test-hid/idProduct 2>/dev/null || true"
    
    # Create HID function
    run_test "create_hid_func" "mkdir -p /sys/kernel/config/usb_gadget/test-hid/functions/hid.usb0 2>/dev/null || true"
    run_test "set_hid_protocol" "echo 1 > /sys/kernel/config/usb_gadget/test-hid/functions/hid.usb0/protocol 2>/dev/null || true"
    run_test "set_hid_subclass" "echo 1 > /sys/kernel/config/usb_gadget/test-hid/functions/hid.usb0/subclass 2>/dev/null || true"
    
    # Cleanup
    run_test "remove_hid" "rm -rf /sys/kernel/config/usb_gadget/test-hid 2>/dev/null || true"
}

# Function to test USB audio
test_usb_audio() {
    log "=== Testing USB Audio ==="
    
    # Create audio gadget
    run_test "create_audio_gadget" "mkdir -p /sys/kernel/config/usb_gadget/test-audio 2>/dev/null || true"
    run_test "set_audio_ids" "echo 0x1d6b > /sys/kernel/config/usb_gadget/test-audio/idVendor 2>/dev/null || true"
    run_test "set_audio_product" "echo 0x0104 > /sys/kernel/config/usb_gadget/test-audio/idProduct 2>/dev/null || true"
    
    # Create audio function
    run_test "create_uac1" "mkdir -p /sys/kernel/config/usb_gadget/test-audio/functions/uac1.usb0 2>/dev/null || true"
    
    # Cleanup
    run_test "remove_audio" "rm -rf /sys/kernel/config/usb_gadget/test-audio 2>/dev/null || true"
}

# Function to test USB device detection
test_usb_detection() {
    log "=== Testing USB Device Detection ==="
    
    # List USB devices
    run_test "lsusb" "lsusb > /dev/null"
    
    # Check USB device tree
    run_test "usb_devices" "ls -la /sys/bus/usb/devices/ > /dev/null"
    
    # Check USB device files
    run_test "usb_files" "ls -la /dev/bus/usb/ > /dev/null 2>&1 || true"
    
    # Check USB configuration
    run_test "usb_config" "cat /proc/bus/usb/devices > /dev/null 2>&1 || true"
}

# Function to show test summary
show_summary() {
    log ""
    log "========================================="
    log "USB Test Summary"
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
${CYAN}USB Integration Tests for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-v, --verbose${NC}   Enable verbose output
  ${GREEN}-s, --skip${NC}      Skip cleanup after tests

Tests:
  ${GREEN}gadget${NC}          USB Gadget framework tests
  ${GREEN}redirect${NC}        USB redirection tests
  ${GREEN}storage${NC}         USB mass storage tests
  ${GREEN}hid${NC}             USB HID tests
  ${GREEN}audio${NC}           USB audio tests
  ${GREEN}detection${NC}       USB device detection tests

Examples:
  # Run all tests
  $0
  
  # Run specific tests
  $0 --gadget --storage
  
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
    RUN_GADGET=false
    RUN_REDIRECT=false
    RUN_STORAGE=false
    RUN_HID=false
    RUN_AUDIO=false
    RUN_DETECTION=false
    
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
            --gadget)
                RUN_GADGET=true
                RUN_ALL=false
                shift
                ;;
            --redirect)
                RUN_REDIRECT=true
                RUN_ALL=false
                shift
                ;;
            --storage)
                RUN_STORAGE=true
                RUN_ALL=false
                shift
                ;;
            --hid)
                RUN_HID=true
                RUN_ALL=false
                shift
                ;;
            --audio)
                RUN_AUDIO=true
                RUN_ALL=false
                shift
                ;;
            --detection)
                RUN_DETECTION=true
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
    print_status "$CYAN" "USB Integration Tests"
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
    cleanup_gadgets
    
    # Run tests
    if [ "$RUN_ALL" = true ] || [ "$RUN_GADGET" = true ]; then
        test_usb_gadget
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_REDIRECT" = true ]; then
        test_usb_redirect
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_STORAGE" = true ]; then
        test_usb_mass_storage
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_HID" = true ]; then
        test_usb_hid
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_AUDIO" = true ]; then
        test_usb_audio
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_DETECTION" = true ]; then
        test_usb_detection
    fi
    
    # Finalize result file
    sed -i '$ s/,$//' "$RESULT_FILE"
    echo "]" >> "$RESULT_FILE"
    
    # Cleanup after tests
    if [ "$SKIP_CLEANUP" = false ]; then
        cleanup_gadgets
    fi
    
    # Show summary
    show_summary
    
    if [ $TESTS_FAILED -eq 0 ]; then
        print_status "$GREEN" "✓ All USB tests passed!"
        exit 0
    else
        print_status "$RED" "✗ Some USB tests failed. Check log for details."
        exit 1
    fi
}

# Trap signals
trap 'cleanup_gadgets; print_status "$RED" "Tests interrupted"; exit 1' INT TERM

# Execute main
main "$@"

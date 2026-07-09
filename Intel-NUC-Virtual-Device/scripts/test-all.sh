#!/bin/bash
# test-all.sh - Run all tests for virtual devices
# 
# This script runs comprehensive tests for all virtual device
# types on the Intel NUC Virtual Device Platform.

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
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${TEST_DIR}/logs/test"
RESULT_DIR="${TEST_DIR}/logs/results"
LOG_FILE="${LOG_DIR}/test_$(date +%Y%m%d_%H%M%S).log"
RESULT_FILE="${RESULT_DIR}/results_$(date +%Y%m%d_%H%M%S).json"

# Create directories
mkdir -p "$LOG_DIR" "$RESULT_DIR"

# Test status counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

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

# Function to check if module is loaded
check_module() {
    local module=$1
    if lsmod | grep -q "$module"; then
        return 0
    else
        return 1
    fi
}

# Function to run a test
run_test() {
    local test_name=$1
    local test_cmd=$2
    local test_type=${3:-"integration"}
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    log "Running test: $test_name"
    log "Command: $test_cmd"
    
    # Create temp file for output
    local output_file="${LOG_DIR}/${test_name}_output.log"
    
    # Run test
    if eval "$test_cmd" > "$output_file" 2>&1; then
        print_status "$GREEN" "  ✓ $test_name PASSED"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        echo "{\"name\":\"$test_name\",\"status\":\"PASSED\",\"type\":\"$test_type\"}" >> "$RESULT_FILE"
        return 0
    else
        print_status "$RED" "  ✗ $test_name FAILED"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "{\"name\":\"$test_name\",\"status\":\"FAILED\",\"type\":\"$test_type\"}" >> "$RESULT_FILE"
        echo "--- Output ---" >> "$LOG_FILE"
        cat "$output_file" >> "$LOG_FILE"
        echo "--- End Output ---" >> "$LOG_FILE"
        return 1
    fi
}

# Function to skip a test
skip_test() {
    local test_name=$1
    local reason=$2
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
    
    print_status "$YELLOW" "  ⚠ $test_name SKIPPED ($reason)"
    echo "{\"name\":\"$test_name\",\"status\":\"SKIPPED\",\"reason\":\"$reason\"}" >> "$RESULT_FILE"
}

# Function to test network devices
test_network() {
    log "=== Testing Network Devices ==="
    
    # Load network drivers
    if ! check_module "veth-driver"; then
        run_test "load_veth_driver" "modprobe veth-driver || insmod ${TEST_DIR}/drivers/virtual-net/veth-driver.ko"
    fi
    
    if ! check_module "bridge-driver"; then
        run_test "load_bridge_driver" "modprobe bridge-driver || insmod ${TEST_DIR}/drivers/virtual-net/bridge-driver.ko"
    fi
    
    # Test veth creation
    run_test "create_veth" "ip link add test-veth type veth peer name test-peer"
    run_test "veth_up" "ip link set test-veth up && ip link set test-peer up"
    run_test "veth_ip" "ip addr add 10.0.0.1/24 dev test-veth && ip addr add 10.0.0.2/24 dev test-peer"
    run_test "veth_ping" "ping -c 3 10.0.0.2"
    run_test "veth_cleanup" "ip link delete test-veth"
    
    # Test bridge
    run_test "create_bridge" "ip link add test-br type bridge"
    run_test "bridge_up" "ip link set test-br up"
    run_test "add_to_bridge" "ip link set test-veth master test-br 2>/dev/null || true"
    run_test "bridge_cleanup" "ip link delete test-br"
}

# Function to test USB devices
test_usb() {
    log "=== Testing USB Devices ==="
    
    # Load USB drivers
    if ! check_module "usb-gadget"; then
        run_test "load_usb_gadget" "modprobe usb-gadget || insmod ${TEST_DIR}/drivers/virtual-usb/usb-gadget.ko"
    fi
    
    if ! check_module "usb-redirect"; then
        run_test "load_usb_redirect" "modprobe usb-redirect || insmod ${TEST_DIR}/drivers/virtual-usb/usb-redirect.ko"
    fi
    
    # Test USB gadget
    if [ -d "/sys/kernel/config/usb_gadget" ]; then
        run_test "usb_gadget_configfs" "test -d /sys/kernel/config/usb_gadget"
        run_test "usb_gadget_create" "mkdir -p /sys/kernel/config/usb_gadget/g1"
    else
        skip_test "usb_gadget_configfs" "ConfigFS not available"
    fi
    
    # Test USB detection
    run_test "usb_list" "lsusb > /dev/null"
}

# Function to test serial devices
test_serial() {
    log "=== Testing Serial Devices ==="
    
    # Load serial drivers
    if ! check_module "pty-manager"; then
        run_test "load_pty_manager" "modprobe pty-manager || insmod ${TEST_DIR}/drivers/virtual-serial/pty-manager.ko"
    fi
    
    if ! check_module "socat-bridge"; then
        run_test "load_socat_bridge" "modprobe socat-bridge || insmod ${TEST_DIR}/drivers/virtual-serial/socat-bridge.ko"
    fi
    
    # Test PTY
    if [ -e "/dev/ttyV0" ]; then
        run_test "pty_exists" "test -e /dev/ttyV0"
        run_test "pty_write" "echo 'test' > /dev/ttyV0 2>/dev/null || true"
    else
        skip_test "pty_exists" "PTY device not created"
    fi
    
    # Test socat
    if command -v socat &> /dev/null; then
        run_test "socat_bridge" "socat -V > /dev/null"
    else
        skip_test "socat_bridge" "socat not installed"
    fi
}

# Function to test disk devices
test_disk() {
    log "=== Testing Disk Devices ==="
    
    # Load disk drivers
    if ! check_module "loop-device"; then
        run_test "load_loop_device" "modprobe loop-device || insmod ${TEST_DIR}/drivers/virtual-disks/loop-device.ko"
    fi
    
    if ! check_module "nbd-server"; then
        run_test "load_nbd_server" "modprobe nbd-server || insmod ${TEST_DIR}/drivers/virtual-disks/nbd-server.ko"
    fi
    
    # Test loop device
    run_test "create_image" "dd if=/dev/zero of=/tmp/test.img bs=1M count=10 2>/dev/null"
    run_test "setup_loop" "losetup /dev/loop99 /tmp/test.img 2>/dev/null || true"
    run_test "format_loop" "mkfs.ext4 /dev/loop99 -F 2>/dev/null || true"
    run_test "mount_loop" "mkdir -p /mnt/test && mount /dev/loop99 /mnt/test 2>/dev/null || true"
    run_test "cleanup_loop" "umount /mnt/test 2>/dev/null; losetup -d /dev/loop99 2>/dev/null; rm /tmp/test.img"
    
    # Test NBD
    if command -v nbd-client &> /dev/null; then
        run_test "nbd_client" "nbd-client -V > /dev/null"
    else
        skip_test "nbd_client" "nbd-client not installed"
    fi
}

# Function to test camera devices
test_camera() {
    log "=== Testing Camera Devices ==="
    
    # Load camera drivers
    if ! check_module "v4l2-driver"; then
        run_test "load_v4l2_driver" "modprobe v4l2-driver || insmod ${TEST_DIR}/drivers/virtual-camera/v4l2-driver.ko"
    fi
    
    if ! check_module "frame-generator"; then
        run_test "load_frame_generator" "modprobe frame-generator || insmod ${TEST_DIR}/drivers/virtual-camera/frame-generator.ko"
    fi
    
    # Test V4L2
    if command -v v4l2-ctl &> /dev/null; then
        run_test "v4l2_list" "v4l2-ctl --list-devices > /dev/null"
        
        if [ -e "/dev/video0" ]; then
            run_test "v4l2_info" "v4l2-ctl -d /dev/video0 --all > /dev/null"
            run_test "v4l2_stream" "timeout 2 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=5 2>/dev/null || true"
        else
            skip_test "v4l2_device" "No video device found"
        fi
    else
        skip_test "v4l2_tools" "v4l2-ctl not installed"
    fi
}

# Function to test audio devices
test_audio() {
    log "=== Testing Audio Devices ==="
    
    # Load audio drivers
    if ! check_module "pipewire-module"; then
        run_test "load_pipewire_module" "modprobe pipewire-module || insmod ${TEST_DIR}/drivers/virtual-audio/pipewire-module.ko"
    fi
    
    if ! check_module "alsa-interface"; then
        run_test "load_alsa_interface" "modprobe alsa-interface || insmod ${TEST_DIR}/drivers/virtual-audio/alsa-interface.ko"
    fi
    
    # Test ALSA
    if command -v aplay &> /dev/null; then
        run_test "alsa_list" "aplay -l > /dev/null"
        run_test "alsa_test" "speaker-test -c 2 -t sine -f 440 -l 1 2>/dev/null || true"
    else
        skip_test "alsa_tools" "aplay not installed"
    fi
    
    # Test PulseAudio
    if command -v pactl &> /dev/null; then
        if pgrep -x "pulseaudio" > /dev/null; then
            run_test "pulseaudio_status" "pactl info > /dev/null"
            run_test "pulseaudio_sinks" "pactl list short sinks > /dev/null"
        else
            skip_test "pulseaudio" "PulseAudio not running"
        fi
    else
        skip_test "pulseaudio_tools" "pactl not installed"
    fi
}

# Function to test performance
test_performance() {
    log "=== Testing Performance ==="
    
    # Test CPU
    run_test "cpu_info" "cat /proc/cpuinfo > /dev/null"
    run_test "cpu_usage" "top -bn1 | grep 'Cpu(s)' > /dev/null"
    
    # Test memory
    run_test "memory_info" "free -h > /dev/null"
    run_test "memory_usage" "vmstat 1 3 > /dev/null"
    
    # Test disk I/O
    run_test "disk_io" "dd if=/dev/zero of=/tmp/test_io bs=1M count=10 2>&1 > /dev/null && rm /tmp/test_io"
    
    # Test network
    run_test "network_speed" "iperf3 -c 127.0.0.1 -t 2 2>/dev/null || true"
}

# Function to show test summary
show_summary() {
    log ""
    log "========================================="
    log "Test Summary"
    log "========================================="
    log ""
    log "Total Tests: $TESTS_TOTAL"
    print_status "$GREEN" "✓ Passed: $TESTS_PASSED"
    print_status "$RED" "✗ Failed: $TESTS_FAILED"
    print_status "$YELLOW" "⚠ Skipped: $TESTS_SKIPPED"
    log ""
    log "Log File: $LOG_FILE"
    log "Results File: $RESULT_FILE"
    log "========================================="
    
    # Return appropriate exit code
    if [ $TESTS_FAILED -eq 0 ]; then
        return 0
    else
        return 1
    fi
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Test Script for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-n, --network${NC}   Only test network devices
  ${GREEN}-u, --usb${NC}       Only test USB devices
  ${GREEN}-s, --serial${NC}    Only test serial devices
  ${GREEN}-d, --disk${NC}      Only test disk devices
  ${GREEN}-c, --camera${NC}    Only test camera devices
  ${GREEN}-a, --audio${NC}     Only test audio devices
  ${GREEN}-p, --perf${NC}      Only test performance
  ${GREEN}-v, --verbose${NC}   Enable verbose output

Examples:
  # Run all tests
  $0
  
  # Only test network and disk
  $0 --network --disk
  
  # Test with verbose output
  $0 --verbose

EOF
}

# Main function
main() {
    # Parse arguments
    TEST_NETWORK=false
    TEST_USB=false
    TEST_SERIAL=false
    TEST_DISK=false
    TEST_CAMERA=false
    TEST_AUDIO=false
    TEST_PERF=false
    TEST_ALL=true
    VERBOSE=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -n|--network)
                TEST_NETWORK=true
                TEST_ALL=false
                shift
                ;;
            -u|--usb)
                TEST_USB=true
                TEST_ALL=false
                shift
                ;;
            -s|--serial)
                TEST_SERIAL=true
                TEST_ALL=false
                shift
                ;;
            -d|--disk)
                TEST_DISK=true
                TEST_ALL=false
                shift
                ;;
            -c|--camera)
                TEST_CAMERA=true
                TEST_ALL=false
                shift
                ;;
            -a|--audio)
                TEST_AUDIO=true
                TEST_ALL=false
                shift
                ;;
            -p|--perf)
                TEST_PERF=true
                TEST_ALL=false
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
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
    print_status "$CYAN" "Intel NUC Virtual Device Platform Tests"
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Test Started: $(date)"
    print_status "$CYAN" "Log File: $LOG_FILE"
    print_status "$CYAN" "========================================="
    echo ""
    
    # Check root
    check_root
    
    # Initialize result file
    echo "[" > "$RESULT_FILE"
    
    # Run tests
    if [ "$TEST_ALL" = true ] || [ "$TEST_NETWORK" = true ]; then
        test_network
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_USB" = true ]; then
        test_usb
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_SERIAL" = true ]; then
        test_serial
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_DISK" = true ]; then
        test_disk
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_CAMERA" = true ]; then
        test_camera
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_AUDIO" = true ]; then
        test_audio
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$TEST_ALL" = true ] || [ "$TEST_PERF" = true ]; then
        test_performance
    fi
    
    # Finalize result file
    # Remove trailing comma if exists
    sed -i '$ s/,$//' "$RESULT_FILE"
    echo "]" >> "$RESULT_FILE"
    
    # Show summary
    show_summary
    
    # Return test result
    if [ $TESTS_FAILED -eq 0 ]; then
        print_status "$GREEN" "✓ All tests passed!"
        exit 0
    else
        print_status "$RED" "✗ Some tests failed. Check log for details."
        exit 1
    fi
}

# Trap signals
trap 'print_status "$RED" "Tests interrupted"; exit 1' INT TERM

# Execute main
main "$@"

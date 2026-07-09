#!/bin/bash
# performance-test.sh - Performance testing for virtual devices
# 
# This script runs comprehensive performance tests for all
# virtual device types on the Intel NUC Virtual Device Platform.

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
LOG_DIR="${TEST_DIR}/logs/performance"
LOG_FILE="${LOG_DIR}/perf_$(date +%Y%m%d_%H%M%S).log"
RESULTS_FILE="${LOG_DIR}/results_$(date +%Y%m%d_%H%M%S).json"

# Create directories
mkdir -p "$LOG_DIR"

# Performance thresholds
NETWORK_THRESHOLD=1000  # Mbps
DISK_READ_THRESHOLD=500  # MB/s
DISK_WRITE_THRESHOLD=300  # MB/s
USB_THRESHOLD=300  # MB/s
CPU_THRESHOLD=80  # Percent
MEMORY_THRESHOLD=80  # Percent

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

# Function to get CPU info
get_cpu_info() {
    log "=== CPU Information ==="
    
    local cpu_model=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | xargs)
    local cpu_cores=$(nproc)
    local cpu_freq=$(lscpu | grep "MHz" | awk '{print $3}')
    
    echo "  CPU Model: $cpu_model"
    echo "  CPU Cores: $cpu_cores"
    echo "  CPU Frequency: ${cpu_freq}MHz"
    
    echo "{\"cpu_model\":\"$cpu_model\",\"cpu_cores\":$cpu_cores,\"cpu_freq\":$cpu_freq}" >> "$RESULTS_FILE"
}

# Function to test CPU performance
test_cpu_performance() {
    log "=== Testing CPU Performance ==="
    
    # Test single-core performance
    log "Testing single-core performance..."
    local single_core_result=$(sysbench cpu --cpu-max-prime=20000 --threads=1 run 2>/dev/null | grep "events per second" | awk '{print $4}')
    
    if [ -n "$single_core_result" ]; then
        log "  Single-core: $single_core_result events/sec"
        echo "{\"cpu_single_core\":$single_core_result}" >> "$RESULTS_FILE"
    else
        log "  Single-core: Failed to measure"
        echo "{\"cpu_single_core\":0}" >> "$RESULTS_FILE"
    fi
    
    # Test multi-core performance
    log "Testing multi-core performance..."
    local multi_core_result=$(sysbench cpu --cpu-max-prime=20000 --threads=$(nproc) run 2>/dev/null | grep "events per second" | awk '{print $4}')
    
    if [ -n "$multi_core_result" ]; then
        log "  Multi-core: $multi_core_result events/sec"
        echo "{\"cpu_multi_core\":$multi_core_result}" >> "$RESULTS_FILE"
    else
        log "  Multi-core: Failed to measure"
        echo "{\"cpu_multi_core\":0}" >> "$RESULTS_FILE"
    fi
}

# Function to test memory performance
test_memory_performance() {
    log "=== Testing Memory Performance ==="
    
    # Test memory bandwidth
    log "Testing memory bandwidth..."
    local mem_result=$(sysbench memory --memory-total-size=10G run 2>/dev/null | grep "MiB/sec" | awk '{print $NF}')
    
    if [ -n "$mem_result" ]; then
        log "  Memory bandwidth: $mem_result MiB/s"
        echo "{\"memory_bandwidth\":$mem_result}" >> "$RESULTS_FILE"
    else
        log "  Memory bandwidth: Failed to measure"
        echo "{\"memory_bandwidth\":0}" >> "$RESULTS_FILE"
    fi
}

# Function to test disk performance
test_disk_performance() {
    log "=== Testing Disk Performance ==="
    
    local test_file="/tmp/perf_test_file"
    local test_size="1G"
    
    # Test sequential read
    log "Testing sequential read performance..."
    local read_result=$(dd if=/dev/zero of=$test_file bs=1M count=1024 conv=fdatasync 2>&1 | grep -o '[0-9.]\+ MB/s' | head -1 | sed 's/ MB\/s//')
    
    if [ -n "$read_result" ]; then
        log "  Sequential read: $read_result MB/s"
        echo "{\"disk_read\":$read_result}" >> "$RESULTS_FILE"
        
        # Check threshold
        if (( $(echo "$read_result > $DISK_READ_THRESHOLD" | bc -l) )); then
            print_status "$GREEN" "  ✓ Read performance meets threshold (>${DISK_READ_THRESHOLD}MB/s)"
        else
            print_status "$YELLOW" "  ⚠ Read performance below threshold (<${DISK_READ_THRESHOLD}MB/s)"
        fi
    else
        log "  Sequential read: Failed to measure"
        echo "{\"disk_read\":0}" >> "$RESULTS_FILE"
    fi
    
    # Test sequential write
    log "Testing sequential write performance..."
    local write_result=$(dd if=$test_file of=/dev/null bs=1M 2>&1 | grep -o '[0-9.]\+ GB/s' | head -1 | sed 's/ GB\/s//')
    
    if [ -n "$write_result" ]; then
        local write_mb=$(echo "$write_result * 1024" | bc)
        log "  Sequential write: $write_mb MB/s"
        echo "{\"disk_write\":$write_mb}" >> "$RESULTS_FILE"
        
        # Check threshold
        if (( $(echo "$write_mb > $DISK_WRITE_THRESHOLD" | bc -l) )); then
            print_status "$GREEN" "  ✓ Write performance meets threshold (>${DISK_WRITE_THRESHOLD}MB/s)"
        else
            print_status "$YELLOW" "  ⚠ Write performance below threshold (<${DISK_WRITE_THRESHOLD}MB/s)"
        fi
    else
        log "  Sequential write: Failed to measure"
        echo "{\"disk_write\":0}" >> "$RESULTS_FILE"
    fi
    
    # Cleanup
    rm -f $test_file
}

# Function to test network performance
test_network_performance() {
    log "=== Testing Network Performance ==="
    
    local test_ip="127.0.0.1"
    local test_port=5201
    
    # Check if iperf3 is installed
    if ! command -v iperf3 &> /dev/null; then
        log "  iperf3 not installed. Installing..."
        apt-get update -qq && apt-get install -y -qq iperf3
    fi
    
    # Start iperf3 server in background
    log "Starting iperf3 server..."
    iperf3 -s -p $test_port > /dev/null 2>&1 &
    local server_pid=$!
    sleep 2
    
    # Test TCP throughput
    log "Testing TCP throughput..."
    local tcp_result=$(iperf3 -c $test_ip -p $test_port -t 5 --json 2>/dev/null | grep -o '"bits_per_second":[0-9.]*' | head -1 | cut -d: -f2)
    
    if [ -n "$tcp_result" ]; then
        local tcp_mbps=$(echo "scale=2; $tcp_result / 1000000" | bc)
        log "  TCP throughput: $tcp_mbps Mbps"
        echo "{\"network_tcp\":$tcp_mbps}" >> "$RESULTS_FILE"
        
        # Check threshold
        if (( $(echo "$tcp_mbps > $NETWORK_THRESHOLD" | bc -l) )); then
            print_status "$GREEN" "  ✓ TCP throughput meets threshold (>${NETWORK_THRESHOLD}Mbps)"
        else
            print_status "$YELLOW" "  ⚠ TCP throughput below threshold (<${NETWORK_THRESHOLD}Mbps)"
        fi
    else
        log "  TCP throughput: Failed to measure"
        echo "{\"network_tcp\":0}" >> "$RESULTS_FILE"
    fi
    
    # Test UDP throughput
    log "Testing UDP throughput..."
    local udp_result=$(iperf3 -c $test_ip -p $test_port -u -t 5 --json 2>/dev/null | grep -o '"bits_per_second":[0-9.]*' | head -1 | cut -d: -f2)
    
    if [ -n "$udp_result" ]; then
        local udp_mbps=$(echo "scale=2; $udp_result / 1000000" | bc)
        log "  UDP throughput: $udp_mbps Mbps"
        echo "{\"network_udp\":$udp_mbps}" >> "$RESULTS_FILE"
    else
        log "  UDP throughput: Failed to measure"
        echo "{\"network_udp\":0}" >> "$RESULTS_FILE"
    fi
    
    # Cleanup
    kill $server_pid 2>/dev/null || true
}

# Function to test USB performance
test_usb_performance() {
    log "=== Testing USB Performance ==="
    
    local test_file="/tmp/usb_test_file"
    
    # Find USB device
    local usb_dev=$(lsblk -l | grep -E "sd[b-z]" | head -1 | awk '{print "/dev/"$1}')
    
    if [ -n "$usb_dev" ] && [ -e "$usb_dev" ]; then
        log "Testing USB device: $usb_dev"
        
        # Test USB read speed
        log "Testing USB read speed..."
        local read_result=$(dd if=$usb_dev of=/dev/null bs=1M count=100 2>&1 | grep -o '[0-9.]\+ MB/s' | head -1 | sed 's/ MB\/s//')
        
        if [ -n "$read_result" ]; then
            log "  USB read: $read_result MB/s"
            echo "{\"usb_read\":$read_result}" >> "$RESULTS_FILE"
            
            # Check threshold
            if (( $(echo "$read_result > $USB_THRESHOLD" | bc -l) )); then
                print_status "$GREEN" "  ✓ USB read meets threshold (>${USB_THRESHOLD}MB/s)"
            else
                print_status "$YELLOW" "  ⚠ USB read below threshold (<${USB_THRESHOLD}MB/s)"
            fi
        else
            log "  USB read: Failed to measure"
            echo "{\"usb_read\":0}" >> "$RESULTS_FILE"
        fi
    else
        log "  No USB device found"
        echo "{\"usb_read\":0}" >> "$RESULTS_FILE"
    fi
}

# Function to test V4L2 performance
test_v4l2_performance() {
    log "=== Testing V4L2 Performance ==="
    
    if [ -e "/dev/video0" ]; then
        # Test frame capture
        log "Testing frame capture..."
        local frame_result=$(timeout 2 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=100 2>&1 | grep "Frames" | awk '{print $2}')
        
        if [ -n "$frame_result" ]; then
            log "  Frames captured: $frame_result"
            echo "{\"v4l2_frames\":$frame_result}" >> "$RESULTS_FILE"
        else
            log "  Frame capture: Failed to measure"
            echo "{\"v4l2_frames\":0}" >> "$RESULTS_FILE"
        fi
    else
        log "  No V4L2 device found"
        echo "{\"v4l2_frames\":0}" >> "$RESULTS_FILE"
    fi
}

# Function to test audio performance
test_audio_performance() {
    log "=== Testing Audio Performance ==="
    
    # Test audio latency
    if command -v paplay &> /dev/null; then
        log "Testing audio latency..."
        local start_time=$(date +%s%N)
        paplay /usr/share/sounds/alsa/Noise.wav 2>/dev/null
        local end_time=$(date +%s%N)
        local latency=$((($end_time - $start_time) / 1000000))
        log "  Audio latency: ${latency}ms"
        echo "{\"audio_latency\":$latency}" >> "$RESULTS_FILE"
    else
        log "  Audio test skipped (paplay not found)"
        echo "{\"audio_latency\":0}" >> "$RESULTS_FILE"
    fi
}

# Function to test overall system performance
test_system_performance() {
    log "=== Testing System Performance ==="
    
    # Check CPU load
    local cpu_load=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d. -f1)
    log "  CPU load: ${cpu_load}%"
    
    # Check memory usage
    local mem_used=$(free | grep Mem | awk '{print $3/$2 * 100.0}' | cut -d. -f1)
    log "  Memory usage: ${mem_used}%"
    
    # Check disk usage
    local disk_used=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
    log "  Disk usage: ${disk_used}%"
    
    echo "{\"cpu_load\":$cpu_load,\"memory_usage\":$mem_used,\"disk_usage\":$disk_used}" >> "$RESULTS_FILE"
    
    # Check thresholds
    if [ "$cpu_load" -gt "$CPU_THRESHOLD" ]; then
        print_status "$YELLOW" "  ⚠ CPU load exceeds threshold (>${CPU_THRESHOLD}%)"
    fi
    
    if [ "$mem_used" -gt "$MEMORY_THRESHOLD" ]; then
        print_status "$YELLOW" "  ⚠ Memory usage exceeds threshold (>${MEMORY_THRESHOLD}%)"
    fi
}

# Function to show summary
show_summary() {
    log ""
    log "========================================="
    log "Performance Test Summary"
    log "========================================="
    log ""
    
    # Parse results
    if [ -f "$RESULTS_FILE" ]; then
        log "CPU Tests:"
        grep -o '"cpu_single_core":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ events\/sec/'
        grep -o '"cpu_multi_core":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ events\/sec/'
        log ""
        
        log "Memory Tests:"
        grep -o '"memory_bandwidth":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ MiB\/s/'
        log ""
        
        log "Disk Tests:"
        grep -o '"disk_read":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ MB\/s/'
        grep -o '"disk_write":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ MB\/s/'
        log ""
        
        log "Network Tests:"
        grep -o '"network_tcp":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ Mbps/'
        grep -o '"network_udp":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ Mbps/'
        log ""
        
        log "USB Tests:"
        grep -o '"usb_read":[0-9.]*' "$RESULTS_FILE" | sed 's/,/ MB\/s/'
        log ""
        
        log "System Tests:"
        grep -o '"cpu_load":[0-9]*' "$RESULTS_FILE" | sed 's/,/ %/'
        grep -o '"memory_usage":[0-9]*' "$RESULTS_FILE" | sed 's/,/ %/'
        grep -o '"disk_usage":[0-9]*' "$RESULTS_FILE" | sed 's/,/ %/'
    fi
    
    log ""
    log "Log File: $LOG_FILE"
    log "Results File: $RESULTS_FILE"
    log "========================================="
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Performance Test Script for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-v, --verbose${NC}   Enable verbose output
  ${GREEN}-o, --output${NC}    Output file for results

Examples:
  # Run all performance tests
  $0
  
  # Run with verbose output
  $0 --verbose
  
  # Save results to specific file
  $0 --output my_results.json

EOF
}

# Main function
main() {
    # Parse arguments
    VERBOSE=false
    OUTPUT_FILE=""
    
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
            -o|--output)
                OUTPUT_FILE="$2"
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
    
    # Override output file if specified
    if [ -n "$OUTPUT_FILE" ]; then
        RESULTS_FILE="$OUTPUT_FILE"
    fi
    
    # Start tests
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Intel NUC Virtual Device Platform Performance Tests"
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Test Started: $(date)"
    print_status "$CYAN" "Log File: $LOG_FILE"
    print_status "$CYAN" "Results File: $RESULTS_FILE"
    print_status "$CYAN" "========================================="
    echo ""
    
    # Check root
    check_root
    
    # Initialize results
    echo "{" > "$RESULTS_FILE"
    
    # Run tests
    get_cpu_info
    echo "," >> "$RESULTS_FILE"
    
    test_system_performance
    echo "," >> "$RESULTS_FILE"
    
    test_cpu_performance
    echo "," >> "$RESULTS_FILE"
    
    test_memory_performance
    echo "," >> "$RESULTS_FILE"
    
    test_disk_performance
    echo "," >> "$RESULTS_FILE"
    
    test_network_performance
    echo "," >> "$RESULTS_FILE"
    
    test_usb_performance
    echo "," >> "$RESULTS_FILE"
    
    test_v4l2_performance
    echo "," >> "$RESULTS_FILE"
    
    test_audio_performance
    
    # Finalize results
    echo "}" >> "$RESULTS_FILE"
    
    # Show summary
    show_summary
    
    print_status "$GREEN" "✓ Performance tests completed"
}

# Trap signals
trap 'print_status "$RED" "Performance tests interrupted"; exit 1' INT TERM

# Execute main
main "$@"

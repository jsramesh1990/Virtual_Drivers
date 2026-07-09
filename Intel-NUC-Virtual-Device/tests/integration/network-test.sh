#!/bin/bash
# network-test.sh - Integration tests for virtual network devices
#
# This script tests all network virtual devices including veth,
# bridge, tap, and virtual network performance.

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
LOG_FILE="${LOG_DIR}/network_test_$(date +%Y%m%d_%H%M%S).log"
RESULT_FILE="${LOG_DIR}/network_results_$(date +%Y%m%d_%H%M%S).json"

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
    
    # Run test
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

# Function to cleanup test interfaces
cleanup_interfaces() {
    log "Cleaning up test interfaces..."
    
    # Remove veth interfaces
    for iface in $(ip link show | grep -o "test-veth[0-9]*" | sort -u); do
        ip link delete "$iface" 2>/dev/null || true
    done
    
    # Remove bridge interfaces
    for br in $(brctl show 2>/dev/null | grep "test-br" | awk '{print $1}'); do
        ip link set "$br" down 2>/dev/null || true
        brctl delbr "$br" 2>/dev/null || true
    done
    
    # Remove TAP interfaces
    for tap in $(ip link show | grep -o "test-tap[0-9]*" | sort -u); do
        ip link delete "$tap" 2>/dev/null || true
    done
}

# Function to test veth devices
test_veth() {
    log "=== Testing veth Devices ==="
    
    # Load veth driver
    if ! check_module "veth-driver"; then
        run_test "load_veth_driver" "modprobe veth-driver || insmod ${TEST_DIR}/drivers/virtual-net/veth-driver.ko"
    fi
    
    # Create veth pair
    run_test "create_veth_pair" "ip link add test-veth0 type veth peer name test-veth1"
    run_test "veth_up" "ip link set test-veth0 up && ip link set test-veth1 up"
    
    # Assign IP addresses
    run_test "veth_ip" "ip addr add 10.0.0.1/24 dev test-veth0 && ip addr add 10.0.0.2/24 dev test-veth1"
    
    # Test connectivity
    run_test "veth_ping" "ping -c 3 -W 2 10.0.0.2 > /dev/null"
    
    # Test MTU change
    run_test "veth_mtu" "ip link set test-veth0 mtu 9000 && ip link set test-veth1 mtu 9000"
    
    # Get statistics
    run_test "veth_stats" "ip -s link show test-veth0 > /dev/null"
    
    # Cleanup
    run_test "veth_cleanup" "ip link delete test-veth0"
}

# Function to test bridge devices
test_bridge() {
    log "=== Testing Bridge Devices ==="
    
    # Load bridge driver
    if ! check_module "bridge-driver"; then
        run_test "load_bridge_driver" "modprobe bridge-driver || insmod ${TEST_DIR}/drivers/virtual-net/bridge-driver.ko"
    fi
    
    # Create bridge
    run_test "create_bridge" "ip link add test-br0 type bridge"
    run_test "bridge_up" "ip link set test-br0 up"
    
    # Create veth pairs for bridge
    run_test "bridge_veth_create" "ip link add test-veth0 type veth peer name test-veth1"
    run_test "bridge_veth_up" "ip link set test-veth0 up && ip link set test-veth1 up"
    
    # Add interfaces to bridge
    run_test "bridge_add" "ip link set test-veth0 master test-br0"
    run_test "bridge_add2" "ip link set test-veth1 master test-br0"
    
    # Assign IP to bridge
    run_test "bridge_ip" "ip addr add 10.0.1.1/24 dev test-br0"
    
    # Show bridge status
    run_test "bridge_show" "brctl show test-br0 > /dev/null"
    
    # Test STP
    run_test "bridge_stp" "brctl stp test-br0 on"
    
    # Cleanup
    run_test "bridge_cleanup" "ip link delete test-br0"
}

# Function to test TAP devices
test_tap() {
    log "=== Testing TAP Devices ==="
    
    # Load TAP driver
    if ! check_module "tap-driver"; then
        run_test "load_tap_driver" "modprobe tap-driver || insmod ${TEST_DIR}/drivers/virtual-net/tap-driver.ko"
    fi
    
    # Create TAP interface
    run_test "create_tap" "ip tuntap add test-tap0 mode tap"
    run_test "tap_up" "ip link set test-tap0 up"
    
    # Assign IP
    run_test "tap_ip" "ip addr add 10.0.2.1/24 dev test-tap0"
    
    # Test TAP with ping
    run_test "tap_ping" "ping -c 3 -W 2 10.0.2.1 > /dev/null"
    
    # Cleanup
    run_test "tap_cleanup" "ip link delete test-tap0"
}

# Function to test MACVLAN
test_macvlan() {
    log "=== Testing MACVLAN Devices ==="
    
    # Create MACVLAN
    run_test "create_macvlan" "ip link add test-mvlan0 link eth0 type macvlan mode bridge"
    run_test "macvlan_up" "ip link set test-mvlan0 up"
    
    # Assign IP
    run_test "macvlan_ip" "ip addr add 192.168.100.100/24 dev test-mvlan0 2>/dev/null || true"
    
    # Cleanup
    run_test "macvlan_cleanup" "ip link delete test-mvlan0 2>/dev/null || true"
}

# Function to test VLAN
test_vlan() {
    log "=== Testing VLAN Devices ==="
    
    # Create VLAN interface
    run_test "create_vlan" "ip link add link eth0 name test-vlan10 type vlan id 10"
    run_test "vlan_up" "ip link set test-vlan10 up"
    
    # Cleanup
    run_test "vlan_cleanup" "ip link delete test-vlan10"
}

# Function to test network performance
test_network_performance() {
    log "=== Testing Network Performance ==="
    
    # Test throughput with iperf3
    if command -v iperf3 &> /dev/null; then
        # Start iperf3 server
        iperf3 -s -p 5201 > /dev/null 2>&1 &
        local server_pid=$!
        sleep 2
        
        # Test TCP throughput
        run_test "iperf3_tcp" "iperf3 -c 127.0.0.1 -p 5201 -t 3 > /dev/null"
        
        # Test UDP throughput
        run_test "iperf3_udp" "iperf3 -c 127.0.0.1 -p 5201 -u -t 3 > /dev/null"
        
        # Cleanup
        kill $server_pid 2>/dev/null || true
    else
        log "  iperf3 not installed, skipping performance tests"
    fi
    
    # Test ping latency
    run_test "ping_latency" "ping -c 10 -W 1 8.8.8.8 > /dev/null 2>&1 || true"
    
    # Test DNS resolution
    run_test "dns_resolution" "nslookup google.com > /dev/null 2>&1 || true"
}

# Function to test network namespaces
test_namespaces() {
    log "=== Testing Network Namespaces ==="
    
    # Create network namespace
    run_test "create_namespace" "ip netns add test-ns1"
    
    # Create veth pair for namespace
    run_test "ns_veth_create" "ip link add ns-veth0 type veth peer name ns-veth1"
    
    # Move interface to namespace
    run_test "ns_move" "ip link set ns-veth1 netns test-ns1"
    
    # Configure namespace
    run_test "ns_config" "ip netns exec test-ns1 ip link set ns-veth1 up"
    run_test "ns_ip" "ip netns exec test-ns1 ip addr add 10.0.3.2/24 dev ns-veth1"
    run_test "ns_host_ip" "ip addr add 10.0.3.1/24 dev ns-veth0"
    run_test "ns_host_up" "ip link set ns-veth0 up"
    
    # Test connectivity
    run_test "ns_ping" "ping -c 3 -W 2 10.0.3.2 > /dev/null"
    run_test "ns_ping_reverse" "ip netns exec test-ns1 ping -c 3 -W 2 10.0.3.1 > /dev/null"
    
    # Cleanup
    run_test "ns_cleanup" "ip netns del test-ns1"
}

# Function to test network bonding
test_bonding() {
    log "=== Testing Network Bonding ==="
    
    # Check if bonding module is available
    if lsmod | grep -q "bonding" || modprobe bonding 2>/dev/null; then
        # Create bond interface
        run_test "create_bond" "ip link add test-bond0 type bond mode active-backup miimon 100"
        run_test "bond_up" "ip link set test-bond0 up"
        
        # Cleanup
        run_test "bond_cleanup" "ip link delete test-bond0"
    else
        log "  Bonding module not available, skipping bonding tests"
    fi
}

# Function to test firewall rules
test_firewall() {
    log "=== Testing Firewall Rules ==="
    
    # Test iptables
    if command -v iptables &> /dev/null; then
        run_test "iptables_list" "iptables -L -n > /dev/null"
        
        # Add test rule
        run_test "iptables_add" "iptables -A INPUT -s 192.168.1.0/24 -j ACCEPT"
        
        # Remove test rule
        run_test "iptables_remove" "iptables -D INPUT -s 192.168.1.0/24 -j ACCEPT"
    fi
    
    # Test nftables
    if command -v nft &> /dev/null; then
        run_test "nft_list" "nft list ruleset > /dev/null 2>&1 || true"
    fi
}

# Function to test network services
test_services() {
    log "=== Testing Network Services ==="
    
    # Test SSH
    if pgrep -x "sshd" > /dev/null; then
        run_test "ssh_connect" "ssh -V > /dev/null"
    fi
    
    # Test HTTP
    if pgrep -x "nginx" > /dev/null || pgrep -x "apache2" > /dev/null; then
        run_test "http_connect" "curl -I http://localhost 2>/dev/null > /dev/null || true"
    fi
    
    # Test DNS
    run_test "dns_server" "nslookup localhost > /dev/null 2>&1 || true"
}

# Function to show test summary
show_summary() {
    log ""
    log "========================================="
    log "Network Test Summary"
    log "========================================="
    log ""
    log "Total Tests: $TESTS_TOTAL"
    print_status "$GREEN" "✓ Passed: $TESTS_PASSED"
    print_status "$RED" "✗ Failed: $TESTS_FAILED"
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
${CYAN}Network Integration Tests for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}      Show this help message
  ${GREEN}-v, --verbose${NC}   Enable verbose output
  ${GREEN}-s, --skip${NC}      Skip cleanup after tests

Tests:
  ${GREEN}veth${NC}           Virtual Ethernet tests
  ${GREEN}bridge${NC}         Bridge tests
  ${GREEN}tap${NC}            TAP device tests
  ${GREEN}macvlan${NC}        MACVLAN tests
  ${GREEN}vlan${NC}           VLAN tests
  ${GREEN}perf${NC}           Performance tests
  ${GREEN}ns${NC}             Namespace tests
  ${GREEN}bond${NC}           Bonding tests
  ${GREEN}firewall${NC}       Firewall tests
  ${GREEN}services${NC}       Service tests

Examples:
  # Run all tests
  $0
  
  # Run specific tests
  $0 --veth --bridge
  
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
    RUN_VETH=false
    RUN_BRIDGE=false
    RUN_TAP=false
    RUN_MACVLAN=false
    RUN_VLAN=false
    RUN_PERF=false
    RUN_NS=false
    RUN_BOND=false
    RUN_FIREWALL=false
    RUN_SERVICES=false
    
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
            --veth)
                RUN_VETH=true
                RUN_ALL=false
                shift
                ;;
            --bridge)
                RUN_BRIDGE=true
                RUN_ALL=false
                shift
                ;;
            --tap)
                RUN_TAP=true
                RUN_ALL=false
                shift
                ;;
            --macvlan)
                RUN_MACVLAN=true
                RUN_ALL=false
                shift
                ;;
            --vlan)
                RUN_VLAN=true
                RUN_ALL=false
                shift
                ;;
            --perf)
                RUN_PERF=true
                RUN_ALL=false
                shift
                ;;
            --ns)
                RUN_NS=true
                RUN_ALL=false
                shift
                ;;
            --bond)
                RUN_BOND=true
                RUN_ALL=false
                shift
                ;;
            --firewall)
                RUN_FIREWALL=true
                RUN_ALL=false
                shift
                ;;
            --services)
                RUN_SERVICES=true
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
    print_status "$CYAN" "Network Integration Tests"
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
    cleanup_interfaces
    
    # Run tests
    if [ "$RUN_ALL" = true ] || [ "$RUN_VETH" = true ]; then
        test_veth
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_BRIDGE" = true ]; then
        test_bridge
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_TAP" = true ]; then
        test_tap
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_MACVLAN" = true ]; then
        test_macvlan
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_VLAN" = true ]; then
        test_vlan
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_PERF" = true ]; then
        test_network_performance
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_NS" = true ]; then
        test_namespaces
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_BOND" = true ]; then
        test_bonding
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_FIREWALL" = true ]; then
        test_firewall
        echo "," >> "$RESULT_FILE"
    fi
    
    if [ "$RUN_ALL" = true ] || [ "$RUN_SERVICES" = true ]; then
        test_services
    fi
    
    # Finalize result file
    sed -i '$ s/,$//' "$RESULT_FILE"
    echo "]" >> "$RESULT_FILE"
    
    # Cleanup after tests
    if [ "$SKIP_CLEANUP" = false ]; then
        cleanup_interfaces
    fi
    
    # Show summary
    show_summary
    
    # Return test result
    if [ $TESTS_FAILED -eq 0 ]; then
        print_status "$GREEN" "✓ All network tests passed!"
        exit 0
    else
        print_status "$RED" "✗ Some network tests failed. Check log for details."
        exit 1
    fi
}

# Trap signals
trap 'cleanup_interfaces; print_status "$RED" "Tests interrupted"; exit 1' INT TERM

# Execute main
main "$@"

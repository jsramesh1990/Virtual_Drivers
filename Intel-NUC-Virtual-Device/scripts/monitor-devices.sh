#!/bin/bash
# monitor-devices.sh - Monitor virtual devices in real-time
# 
# This script provides real-time monitoring of all virtual
# devices on the Intel NUC Virtual Device Platform.

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
MONITOR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${MONITOR_DIR}/logs/monitor"
LOG_FILE="${LOG_DIR}/monitor_$(date +%Y%m%d_%H%M%S).log"
REFRESH_INTERVAL=2  # seconds

# Create directories
mkdir -p "$LOG_DIR"

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

# Function to monitor network devices
monitor_network() {
    echo -e "\n${CYAN}=== Network Devices ===${NC}"
    
    # Show all network interfaces
    echo -e "${BLUE}Network Interfaces:${NC}"
    ip -br link show | grep -E "veth|br|tap|docker|eth|wlan" | while read line; do
        echo "  $line"
    done
    
    # Show routing table
    echo -e "\n${BLUE}Routing Table:${NC}"
    ip route show | head -10
    
    # Show network statistics
    echo -e "\n${BLUE}Network Statistics:${NC}"
    netstat -i | head -10
}

# Function to monitor USB devices
monitor_usb() {
    echo -e "\n${CYAN}=== USB Devices ===${NC}"
    
    # Show USB devices
    echo -e "${BLUE}USB Devices:${NC}"
    lsusb
    
    # Show USB gadget status
    if [ -d "/sys/kernel/config/usb_gadget" ]; then
        echo -e "\n${BLUE}USB Gadgets:${NC}"
        ls -la /sys/kernel/config/usb_gadget/ 2>/dev/null | grep -v "^total" | while read line; do
            echo "  $line"
        done
    fi
    
    # Show USB devices in /dev
    echo -e "\n${BLUE}USB Device Files:${NC}"
    ls -la /dev/usb* 2>/dev/null || echo "  No USB device files"
}

# Function to monitor serial devices
monitor_serial() {
    echo -e "\n${CYAN}=== Serial Devices ===${NC}"
    
    # Show serial ports
    echo -e "${BLUE}Serial Ports:${NC}"
    ls -la /dev/ttyV* 2>/dev/null || echo "  No virtual serial ports"
    ls -la /dev/ttyS* 2>/dev/null | head -10 || echo "  No serial ports"
    ls -la /dev/ttyUSB* 2>/dev/null || echo "  No USB serial ports"
}

# Function to monitor disk devices
monitor_disk() {
    echo -e "\n${CYAN}=== Disk Devices ===${NC}"
    
    # Show block devices
    echo -e "${BLUE}Block Devices:${NC}"
    lsblk | head -20
    
    # Show loop devices
    echo -e "\n${BLUE}Loop Devices:${NC}"
    losetup -a 2>/dev/null || echo "  No loop devices in use"
    
    # Show mounted filesystems
    echo -e "\n${BLUE}Mounted Filesystems:${NC}"
    df -h | head -15
    
    # Show NBD devices
    echo -e "\n${BLUE}NBD Devices:${NC}"
    ls -la /dev/nbd* 2>/dev/null || echo "  No NBD devices"
}

# Function to monitor camera devices
monitor_camera() {
    echo -e "\n${CYAN}=== Camera Devices ===${NC}"
    
    # Show V4L2 devices
    echo -e "${BLUE}V4L2 Devices:${NC}"
    v4l2-ctl --list-devices 2>/dev/null || echo "  No V4L2 devices"
    
    # Show video devices
    echo -e "\n${BLUE}Video Device Files:${NC}"
    ls -la /dev/video* 2>/dev/null || echo "  No video devices"
    
    # Show frame generator status
    if [ -f "/sys/module/frame_generator/parameters/fg_pattern" ]; then
        echo -e "\n${BLUE}Frame Generator:${NC}"
        echo "  Pattern: $(cat /sys/module/frame_generator/parameters/fg_pattern 2>/dev/null || echo 'N/A')"
        echo "  Width: $(cat /sys/module/frame_generator/parameters/fg_width 2>/dev/null || echo 'N/A')"
        echo "  Height: $(cat /sys/module/frame_generator/parameters/fg_height 2>/dev/null || echo 'N/A')"
        echo "  FPS: $(cat /sys/module/frame_generator/parameters/fg_fps 2>/dev/null || echo 'N/A')"
    fi
}

# Function to monitor audio devices
monitor_audio() {
    echo -e "\n${CYAN}=== Audio Devices ===${NC}"
    
    # Show ALSA devices
    echo -e "${BLUE}ALSA Devices:${NC}"
    aplay -l 2>/dev/null | head -10 || echo "  No ALSA devices"
    arecord -l 2>/dev/null | head -10 || echo "  No ALSA capture devices"
    
    # Show PulseAudio devices
    if command -v pactl &> /dev/null; then
        echo -e "\n${BLUE}PulseAudio Sinks:${NC}"
        pactl list short sinks | head -10
        
        echo -e "\n${BLUE}PulseAudio Sources:${NC}"
        pactl list short sources | head -10
    fi
    
    # Show audio processes
    echo -e "\n${BLUE}Audio Processes:${NC}"
    ps aux | grep -E "pulse|pipewire|alsa" | grep -v grep | head -10
}

# Function to monitor system resources
monitor_system() {
    echo -e "\n${CYAN}=== System Resources ===${NC}"
    
    # CPU usage
    echo -e "${BLUE}CPU Usage:${NC}"
    top -bn1 | grep "Cpu(s)" | head -1
    
    # Memory usage
    echo -e "\n${BLUE}Memory Usage:${NC}"
    free -h
    
    # Load average
    echo -e "\n${BLUE}Load Average:${NC}"
    uptime
    
    # Processes
    echo -e "\n${BLUE}Running Processes:${NC}"
    ps aux | wc -l
}

# Function to monitor kernel modules
monitor_modules() {
    echo -e "\n${CYAN}=== Kernel Modules ===${NC}"
    
    # Show loaded virtual device modules
    echo -e "${BLUE}Virtual Device Modules:${NC}"
    lsmod | grep -E "veth|bridge|tap|usb-gadget|usb-redirect|pty|socat|loop|nbd|v4l2|frame-generator|pipewire|alsa" || echo "  No virtual device modules loaded"
}

# Function to monitor devices in /dev
monitor_dev_files() {
    echo -e "\n${CYAN}=== Device Files ===${NC}"
    
    # Show virtual device files
    echo -e "${BLUE}Virtual Device Files:${NC}"
    
    # Network
    echo -e "\n${GREEN}Network:${NC}"
    ls -la /sys/class/net/ | grep -E "veth|br|tap" | head -10
    
    # USB
    echo -e "\n${GREEN}USB:${NC}"
    ls -la /dev/bus/usb/ 2>/dev/null | head -10
    
    # Serial
    echo -e "\n${GREEN}Serial:${NC}"
    ls -la /dev/ttyV* 2>/dev/null || echo "  No virtual serial devices"
    
    # Disk
    echo -e "\n${GREEN}Disk:${NC}"
    ls -la /dev/loop* 2>/dev/null | head -10
    ls -la /dev/nbd* 2>/dev/null || echo "  No NBD devices"
    
    # Camera
    echo -e "\n${GREEN}Camera:${NC}"
    ls -la /dev/video* 2>/dev/null || echo "  No video devices"
    
    # Audio
    echo -e "\n${GREEN}Audio:${NC}"
    ls -la /dev/snd/ 2>/dev/null | head -10
}

# Function to show all monitoring
monitor_all() {
    clear
    echo -e "${CYAN}========================================="
    echo -e "Virtual Device Monitor"
    echo -e "Time: $(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "=========================================${NC}"
    
    monitor_system
    monitor_modules
    monitor_network
    monitor_usb
    monitor_serial
    monitor_disk
    monitor_camera
    monitor_audio
    monitor_dev_files
    
    echo -e "\n${CYAN}========================================="
    echo -e "Press Ctrl+C to exit"
    echo -e "=========================================${NC}"
}

# Function to show continuous monitoring
continuous_monitor() {
    while true; do
        monitor_all
        sleep "$REFRESH_INTERVAL"
    done
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Device Monitor Script for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}              Show this help message
  ${GREEN}-i, --interval${NC} SECONDS  Refresh interval (default: 2)
  ${GREEN}-o, --once${NC}              Run once and exit
  ${GREEN}-f, --filter${NC} TYPE       Filter by device type:
                                      network, usb, serial, disk, camera, audio, system, modules, dev

Examples:
  # Continuous monitoring
  $0
  
  # Run once
  $0 --once
  
  # Monitor only network devices
  $0 --filter network
  
  # Monitor with 5 second interval
  $0 --interval 5

EOF
}

# Main function
main() {
    # Parse arguments
    RUN_ONCE=false
    FILTER="all"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -i|--interval)
                REFRESH_INTERVAL="$2"
                shift 2
                ;;
            -o|--once)
                RUN_ONCE=true
                shift
                ;;
            -f|--filter)
                FILTER="$2"
                shift 2
                ;;
            *)
                print_status "$RED" "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Check root
    check_root
    
    # Log start
    log "Starting device monitor (filter: $FILTER, interval: ${REFRESH_INTERVAL}s)"
    
    # Run monitor
    if [ "$RUN_ONCE" = true ]; then
        if [ "$FILTER" = "all" ]; then
            monitor_all
        else
            case $FILTER in
                network) monitor_network ;;
                usb) monitor_usb ;;
                serial) monitor_serial ;;
                disk) monitor_disk ;;
                camera) monitor_camera ;;
                audio) monitor_audio ;;
                system) monitor_system ;;
                modules) monitor_modules ;;
                dev) monitor_dev_files ;;
                *)
                    print_status "$RED" "Unknown filter: $FILTER"
                    show_usage
                    exit 1
                    ;;
            esac
        fi
    else
        continuous_monitor
    fi
}

# Trap signals
trap 'log "Monitor stopped"; exit 0' INT TERM

# Execute main
main "$@"

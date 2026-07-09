#!/bin/bash
# cleanup.sh - Clean up all virtual devices and resources
# 
# This script cleans up all virtual devices, kernel modules,
# and temporary files created by the Intel NUC Virtual Device Platform.

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
CLEANUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${CLEANUP_DIR}/logs/cleanup_$(date +%Y%m%d_%H%M%S).log"
IMAGE_DIR="${HOME}/virtual-disk-images"
MOUNT_BASE="/mnt"

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

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

# Function to cleanup network devices
cleanup_network() {
    log "Cleaning up network devices..."
    
    # Remove veth interfaces
    for iface in $(ip link show | grep -o "veth[0-9]*" | sort -u); do
        if [ -n "$iface" ]; then
            log "  Removing veth: $iface"
            ip link delete "$iface" 2>/dev/null || true
        fi
    done
    
    # Remove bridge interfaces
    for br in $(brctl show 2>/dev/null | grep -v "bridge name" | awk '{print $1}'); do
        if [ -n "$br" ]; then
            log "  Removing bridge: $br"
            ip link set "$br" down 2>/dev/null || true
            brctl delbr "$br" 2>/dev/null || true
        fi
    done
    
    # Remove TAP interfaces
    for tap in $(ip link show | grep -o "tap[0-9]*" | sort -u); do
        if [ -n "$tap" ]; then
            log "  Removing TAP: $tap"
            ip link delete "$tap" 2>/dev/null || true
        fi
    done
    
    # Remove NAT rules
    iptables -t nat -F 2>/dev/null || true
    iptables -F 2>/dev/null || true
    
    log "Network devices cleaned up"
}

# Function to cleanup USB devices
cleanup_usb() {
    log "Cleaning up USB devices..."
    
    # Remove USB gadgets
    if [ -d "/sys/kernel/config/usb_gadget" ]; then
        for gadget in $(ls /sys/kernel/config/usb_gadget/ 2>/dev/null); do
            if [ -n "$gadget" ]; then
                log "  Removing USB gadget: $gadget"
                echo "" > /sys/kernel/config/usb_gadget/$gadget/UDC 2>/dev/null || true
                rm -rf /sys/kernel/config/usb_gadget/$gadget 2>/dev/null || true
            fi
        done
    fi
    
    # Unload USB modules
    modprobe -r usb-gadget 2>/dev/null || true
    modprobe -r usb-redirect 2>/dev/null || true
    
    log "USB devices cleaned up"
}

# Function to cleanup serial devices
cleanup_serial() {
    log "Cleaning up serial devices..."
    
    # Remove PTY devices
    for pty in /dev/ttyV*; do
        if [ -e "$pty" ]; then
            log "  Removing PTY: $pty"
            rm -f "$pty" 2>/dev/null || true
        fi
    done
    
    # Unload serial modules
    modprobe -r socat-bridge 2>/dev/null || true
    modprobe -r pty-manager 2>/dev/null || true
    
    log "Serial devices cleaned up"
}

# Function to cleanup disk devices
cleanup_disk() {
    log "Cleaning up disk devices..."
    
    # Unmount all loop devices
    for mount in $(mount | grep "$MOUNT_BASE" | awk '{print $3}'); do
        if [ -n "$mount" ]; then
            log "  Unmounting: $mount"
            umount "$mount" 2>/dev/null || true
        fi
    done
    
    # Detach all loop devices
    for loop in $(losetup -a 2>/dev/null | cut -d: -f1); do
        if [ -n "$loop" ]; then
            log "  Detaching loop: $loop"
            losetup -d "$loop" 2>/dev/null || true
        fi
    done
    
    # Remove disk images
    if [ -d "$IMAGE_DIR" ]; then
        log "  Removing disk images from $IMAGE_DIR"
        rm -rf "$IMAGE_DIR"/*.img 2>/dev/null || true
    fi
    
    # Unload disk modules
    modprobe -r nbd-server 2>/dev/null || true
    modprobe -r loop-device 2>/dev/null || true
    
    log "Disk devices cleaned up"
}

# Function to cleanup camera devices
cleanup_camera() {
    log "Cleaning up camera devices..."
    
    # Remove V4L2 devices
    for video in /dev/video*; do
        if [ -e "$video" ]; then
            log "  Removing video device: $video"
            rm -f "$video" 2>/dev/null || true
        fi
    done
    
    # Unload camera modules
    modprobe -r frame-generator 2>/dev/null || true
    modprobe -r v4l2-driver 2>/dev/null || true
    modprobe -r v4l2loopback 2>/dev/null || true
    
    log "Camera devices cleaned up"
}

# Function to cleanup audio devices
cleanup_audio() {
    log "Cleaning up audio devices..."
    
    # Unload PulseAudio modules
    if command -v pactl &> /dev/null; then
        for module in $(pactl list short modules 2>/dev/null | grep -E "null-sink|null-source|loopback" | awk '{print $1}'); do
            if [ -n "$module" ]; then
                log "  Unloading PulseAudio module: $module"
                pactl unload-module "$module" 2>/dev/null || true
            fi
        done
    fi
    
    # Unload audio modules
    modprobe -r alsa-interface 2>/dev/null || true
    modprobe -r pipewire-module 2>/dev/null || true
    modprobe -r snd-aloop 2>/dev/null || true
    modprobe -r snd-dummy 2>/dev/null || true
    
    log "Audio devices cleaned up"
}

# Function to cleanup kernel modules
cleanup_modules() {
    log "Cleaning up kernel modules..."
    
    # List all virtual device modules
    modules=(
        "veth-driver"
        "bridge-driver"
        "tap-driver"
        "usb-gadget"
        "usb-redirect"
        "pty-manager"
        "socat-bridge"
        "loop-device"
        "nbd-server"
        "v4l2-driver"
        "frame-generator"
        "pipewire-module"
        "alsa-interface"
    )
    
    # Unload modules in reverse order
    for module in "${modules[@]}"; do
        if lsmod | grep -q "$module"; then
            log "  Unloading module: $module"
            modprobe -r "$module" 2>/dev/null || true
        fi
    done
    
    log "Kernel modules cleaned up"
}

# Function to cleanup temporary files
cleanup_temp() {
    log "Cleaning up temporary files..."
    
    # Remove temporary files
    rm -f /tmp/*.img 2>/dev/null || true
    rm -f /tmp/*.log 2>/dev/null || true
    rm -f /tmp/nbd_* 2>/dev/null || true
    rm -f /tmp/usb_* 2>/dev/null || true
    rm -f /tmp/loop-mounts.txt 2>/dev/null || true
    rm -f /tmp/socat-example.pid 2>/dev/null || true
    
    # Remove Python cache
    find "$CLEANUP_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$CLEANUP_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true
    
    log "Temporary files cleaned up"
}

# Function to cleanup all
cleanup_all() {
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Intel NUC Virtual Device Platform Cleanup"
    print_status "$CYAN" "========================================="
    print_status "$CYAN" "Started: $(date)"
    print_status "$CYAN" "Log File: $LOG_FILE"
    print_status "$CYAN" "========================================="
    echo ""
    
    # Check root
    check_root
    
    # Confirmation
    echo -e "${YELLOW}This will remove all virtual devices and clean up resources.${NC}"
    read -p "Continue? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "$YELLOW" "Cleanup cancelled"
        exit 0
    fi
    
    # Cleanup all components
    cleanup_network
    cleanup_usb
    cleanup_serial
    cleanup_disk
    cleanup_camera
    cleanup_audio
    cleanup_modules
    cleanup_temp
    
    print_status "$CYAN" "========================================="
    print_status "$GREEN" "✓ Cleanup completed successfully"
    print_status "$CYAN" "Finished: $(date)"
    print_status "$CYAN" "========================================="
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Cleanup Script for Intel NUC Virtual Device Platform${NC}

Usage: $0 [options]

Options:
  ${GREEN}-h, --help${NC}              Show this help message
  ${GREEN}-f, --force${NC}             Force cleanup without confirmation
  ${GREEN}-n, --network${NC}           Only cleanup network devices
  ${GREEN}-u, --usb${NC}               Only cleanup USB devices
  ${GREEN}-s, --serial${NC}            Only cleanup serial devices
  ${GREEN}-d, --disk${NC}              Only cleanup disk devices
  ${GREEN}-c, --camera${NC}            Only cleanup camera devices
  ${GREEN}-a, --audio${NC}             Only cleanup audio devices
  ${GREEN}-m, --modules${NC}           Only cleanup kernel modules
  ${GREEN}-t, --temp${NC}              Only cleanup temporary files

Examples:
  # Cleanup everything
  $0
  
  # Force cleanup without confirmation
  $0 --force
  
  # Cleanup only network and disk
  $0 --network --disk

EOF
}

# Main function
main() {
    # Parse arguments
    FORCE=false
    CLEAN_NETWORK=false
    CLEAN_USB=false
    CLEAN_SERIAL=false
    CLEAN_DISK=false
    CLEAN_CAMERA=false
    CLEAN_AUDIO=false
    CLEAN_MODULES=false
    CLEAN_TEMP=false
    CLEAN_ALL=true
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            -n|--network)
                CLEAN_NETWORK=true
                CLEAN_ALL=false
                shift
                ;;
            -u|--usb)
                CLEAN_USB=true
                CLEAN_ALL=false
                shift
                ;;
            -s|--serial)
                CLEAN_SERIAL=true
                CLEAN_ALL=false
                shift
                ;;
            -d|--disk)
                CLEAN_DISK=true
                CLEAN_ALL=false
                shift
                ;;
            -c|--camera)
                CLEAN_CAMERA=true
                CLEAN_ALL=false
                shift
                ;;
            -a|--audio)
                CLEAN_AUDIO=true
                CLEAN_ALL=false
                shift
                ;;
            -m|--modules)
                CLEAN_MODULES=true
                CLEAN_ALL=false
                shift
                ;;
            -t|--temp)
                CLEAN_TEMP=true
                CLEAN_ALL=false
                shift
                ;;
            *)
                print_status "$RED" "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # If force, skip confirmation
    if [ "$FORCE" = true ]; then
        # Run specific cleanup
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_NETWORK" = true ]; then cleanup_network; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_USB" = true ]; then cleanup_usb; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_SERIAL" = true ]; then cleanup_serial; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_DISK" = true ]; then cleanup_disk; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_CAMERA" = true ]; then cleanup_camera; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_AUDIO" = true ]; then cleanup_audio; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_MODULES" = true ]; then cleanup_modules; fi
        if [ "$CLEAN_ALL" = true ] || [ "$CLEAN_TEMP" = true ]; then cleanup_temp; fi
        
        print_status "$GREEN" "✓ Cleanup completed"
        exit 0
    fi
    
    # Run full cleanup with confirmation
    cleanup_all
}

# Trap signals
trap 'print_status "$RED" "Cleanup interrupted"; exit 1' INT TERM

# Execute main
main "$@"

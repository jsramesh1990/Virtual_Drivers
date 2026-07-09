#!/bin/bash
# loop-mount.sh - Loop device management and mounting script
# 
# This script provides comprehensive loop device management for
# mounting disk images, ISO files, and creating virtual disks
# on Intel NUC platforms.

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
LOOP_BASE="/dev/loop"
MOUNT_BASE="/mnt"
IMAGE_DIR="${HOME}/virtual-disk-images"
MAX_LOOP_DEVICES=256

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${RED}✗${NC} Please run as root"
        exit 1
    fi
}

# Function to create image directory
create_image_dir() {
    if [ ! -d "$IMAGE_DIR" ]; then
        echo -e "${BLUE}→${NC} Creating image directory: $IMAGE_DIR"
        mkdir -p "$IMAGE_DIR"
    fi
}

# Function to find free loop device
find_free_loop() {
    local start=${1:-0}
    local end=${2:-$MAX_LOOP_DEVICES}
    
    for i in $(seq $start $end); do
        local dev="${LOOP_BASE}${i}"
        if [ ! -e "$dev" ]; then
            echo "$dev"
            return 0
        fi
        # Check if device is in use
        if ! losetup "$dev" 2>/dev/null | grep -q "$dev"; then
            echo "$dev"
            return 0
        fi
    done
    return 1
}

# Function to create disk image
create_image() {
    local name=$1
    local size=$2
    local image_path="${IMAGE_DIR}/${name}.img"
    
    echo -e "${BLUE}→${NC} Creating disk image: $name ($size)"
    
    # Check if image already exists
    if [ -f "$image_path" ]; then
        echo -e "${YELLOW}⚠${NC} Image already exists: $image_path"
        read -p "Overwrite? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
    fi
    
    # Create image with dd
    echo -e "${BLUE}→${NC} Creating image file..."
    dd if=/dev/zero of="$image_path" bs=1M count="$size" status=progress
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Image created: $image_path"
        echo -e "${GREEN}✓${NC} Size: ${size}MB"
    else
        echo -e "${RED}✗${NC} Failed to create image"
        return 1
    fi
}

# Function to format image
format_image() {
    local image_path=$1
    local fs_type=${2:-ext4}
    
    echo -e "${BLUE}→${NC} Formatting image: $image_path ($fs_type)"
    
    if [ ! -f "$image_path" ]; then
        echo -e "${RED}✗${NC} Image not found: $image_path"
        return 1
    fi
    
    # Setup loop device
    local loop_dev=$(losetup -f --show "$image_path")
    if [ -z "$loop_dev" ]; then
        echo -e "${RED}✗${NC} Failed to setup loop device"
        return 1
    fi
    
    echo -e "${BLUE}→${NC} Loop device: $loop_dev"
    
    # Format the device
    echo -e "${BLUE}→${NC} Formatting with $fs_type..."
    mkfs.$fs_type "$loop_dev" -F
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Format complete"
    else
        echo -e "${RED}✗${NC} Format failed"
        losetup -d "$loop_dev"
        return 1
    fi
    
    # Detach loop device
    losetup -d "$loop_dev"
    echo -e "${GREEN}✓${NC} Loop device detached"
}

# Function to mount image
mount_image() {
    local image_path=$1
    local mount_point=$2
    
    echo -e "${BLUE}→${NC} Mounting image: $image_path"
    
    if [ ! -f "$image_path" ]; then
        echo -e "${RED}✗${NC} Image not found: $image_path"
        return 1
    fi
    
    # Create mount point
    if [ -z "$mount_point" ]; then
        mount_point="${MOUNT_BASE}/$(basename "$image_path" .img)"
    fi
    
    if [ ! -d "$mount_point" ]; then
        mkdir -p "$mount_point"
        echo -e "${BLUE}→${NC} Created mount point: $mount_point"
    fi
    
    # Setup loop device
    local loop_dev=$(losetup -f --show "$image_path")
    if [ -z "$loop_dev" ]; then
        echo -e "${RED}✗${NC} Failed to setup loop device"
        return 1
    fi
    
    echo -e "${BLUE}→${NC} Loop device: $loop_dev"
    
    # Check if formatted
    if ! blkid "$loop_dev" 2>/dev/null | grep -q "TYPE"; then
        echo -e "${YELLOW}⚠${NC} Image appears unformatted"
        read -p "Format before mounting? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            format_image "$image_path"
            # Reattach loop device
            loop_dev=$(losetup -f --show "$image_path")
        fi
    fi
    
    # Mount the device
    echo -e "${BLUE}→${NC} Mounting to: $mount_point"
    mount "$loop_dev" "$mount_point"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Image mounted successfully"
        echo -e "${GREEN}✓${NC} Mount point: $mount_point"
        echo -e "${GREEN}✓${NC} Loop device: $loop_dev"
        
        # Save mount info
        echo "$loop_dev:$mount_point:$image_path" >> /tmp/loop-mounts.txt
    else
        echo -e "${RED}✗${NC} Mount failed"
        losetup -d "$loop_dev"
        return 1
    fi
}

# Function to mount ISO file
mount_iso() {
    local iso_path=$1
    local mount_point=$2
    
    echo -e "${BLUE}→${NC} Mounting ISO: $iso_path"
    
    if [ ! -f "$iso_path" ]; then
        echo -e "${RED}✗${NC} ISO not found: $iso_path"
        return 1
    fi
    
    # Create mount point
    if [ -z "$mount_point" ]; then
        mount_point="${MOUNT_BASE}/iso_$(basename "$iso_path" .iso)"
    fi
    
    if [ ! -d "$mount_point" ]; then
        mkdir -p "$mount_point"
    fi
    
    # Mount ISO with loop
    mount -o loop "$iso_path" "$mount_point"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} ISO mounted successfully"
        echo -e "${GREEN}✓${NC} Mount point: $mount_point"
    else
        echo -e "${RED}✗${NC} Failed to mount ISO"
        return 1
    fi
}

# Function to unmount image
unmount_image() {
    local mount_point=$1
    
    echo -e "${BLUE}→${NC} Unmounting: $mount_point"
    
    if [ ! -d "$mount_point" ]; then
        echo -e "${RED}✗${NC} Mount point not found: $mount_point"
        return 1
    fi
    
    # Find loop device
    local loop_dev=$(mount | grep "$mount_point" | awk '{print $1}')
    if [ -z "$loop_dev" ]; then
        echo -e "${RED}✗${NC} No device mounted at $mount_point"
        return 1
    fi
    
    # Unmount
    umount "$mount_point"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Unmounted: $mount_point"
        
        # Detach loop device
        if [[ "$loop_dev" == /dev/loop* ]]; then
            losetup -d "$loop_dev" 2>/dev/null
            echo -e "${GREEN}✓${NC} Loop device detached: $loop_dev"
        fi
        
        # Remove from saved mounts
        sed -i "/$mount_point/d" /tmp/loop-mounts.txt 2>/dev/null
        
        # Optionally remove mount point
        read -p "Remove mount point directory? (y/n): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rmdir "$mount_point" 2>/dev/null
            echo -e "${GREEN}✓${NC} Removed mount point"
        fi
    else
        echo -e "${RED}✗${NC} Unmount failed"
        return 1
    fi
}

# Function to show mounted images
show_mounted() {
    echo -e "\n${CYAN}=== Mounted Loop Devices ===${NC}"
    echo ""
    
    if [ -f /tmp/loop-mounts.txt ]; then
        while IFS=':' read -r loop mount image; do
            echo -e "${GREEN}✓${NC} $loop -> $mount"
            echo -e "    Image: $image"
            echo -e "    Usage: $(df -h "$mount" | tail -1)"
            echo ""
        done < /tmp/loop-mounts.txt
    else
        echo -e "${YELLOW}⚠${NC} No loop devices currently mounted"
    fi
    
    echo -e "\n${CYAN}All Loop Devices:${NC}"
    losetup -a
}

# Function to resize image
resize_image() {
    local image_path=$1
    local new_size=$2
    
    echo -e "${BLUE}→${NC} Resizing image: $image_path to ${new_size}MB"
    
    if [ ! -f "$image_path" ]; then
        echo -e "${RED}✗${NC} Image not found: $image_path"
        return 1
    fi
    
    # Check if image is mounted
    if grep -q "$image_path" /tmp/loop-mounts.txt; then
        echo -e "${RED}✗${NC} Image is currently mounted. Unmount first."
        return 1
    fi
    
    # Get current size
    local current_size=$(stat -c%s "$image_path")
    local current_mb=$((current_size / 1024 / 1024))
    
    echo -e "${BLUE}→${NC} Current size: ${current_mb}MB"
    
    if [ $new_size -eq $current_mb ]; then
        echo -e "${YELLOW}⚠${NC} New size same as current size"
        return 0
    fi
    
    # Resize image
    if [ $new_size -gt $current_mb ]; then
        # Expand
        dd if=/dev/zero bs=1M count=$((new_size - current_mb)) >> "$image_path"
    else
        # Shrink - warn user
        echo -e "${RED}⚠${NC} Shrinking can cause data loss!"
        read -p "Continue? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            return 1
        fi
        
        # Use truncate to shrink
        truncate -s ${new_size}M "$image_path"
    fi
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Image resized to ${new_size}MB"
        
        # Resize filesystem if image is formatted
        if file "$image_path" | grep -q "filesystem"; then
            echo -e "${BLUE}→${NC} Resizing filesystem..."
            local loop_dev=$(losetup -f --show "$image_path")
            resize2fs "$loop_dev" ${new_size}M
            losetup -d "$loop_dev"
            echo -e "${GREEN}✓${NC} Filesystem resized"
        fi
    else
        echo -e "${RED}✗${NC} Resize failed"
        return 1
    fi
}

# Function to create encrypted image
create_encrypted_image() {
    local name=$1
    local size=$2
    local image_path="${IMAGE_DIR}/${name}.enc.img"
    
    echo -e "${BLUE}→${NC} Creating encrypted image: $name ($size)"
    
    # Create image
    dd if=/dev/zero of="$image_path" bs=1M count="$size" status=progress
    
    # Setup loop device
    local loop_dev=$(losetup -f --show "$image_path")
    
    # Setup encryption with LUKS
    echo -e "${BLUE}→${NC} Setting up LUKS encryption..."
    cryptsetup luksFormat "$loop_dev"
    
    # Open encrypted device
    cryptsetup open "$loop_dev" "${name}_enc"
    
    # Format
    mkfs.ext4 "/dev/mapper/${name}_enc"
    
    # Close device
    cryptsetup close "${name}_enc"
    losetup -d "$loop_dev"
    
    echo -e "${GREEN}✓${NC} Encrypted image created: $image_path"
}

# Function to mount encrypted image
mount_encrypted() {
    local image_path=$1
    local mount_point=$2
    local name=$(basename "$image_path" .enc.img)
    
    echo -e "${BLUE}→${NC} Mounting encrypted image: $image_path"
    
    if [ ! -f "$image_path" ]; then
        echo -e "${RED}✗${NC} Image not found: $image_path"
        return 1
    fi
    
    # Setup loop device
    local loop_dev=$(losetup -f --show "$image_path")
    
    # Open encrypted device
    echo -e "${BLUE}→${NC} Opening encrypted device..."
    cryptsetup open "$loop_dev" "${name}_enc"
    
    # Create mount point
    if [ -z "$mount_point" ]; then
        mount_point="${MOUNT_BASE}/${name}_enc"
    fi
    
    if [ ! -d "$mount_point" ]; then
        mkdir -p "$mount_point"
    fi
    
    # Mount
    mount "/dev/mapper/${name}_enc" "$mount_point"
    
    echo -e "${GREEN}✓${NC} Encrypted image mounted to $mount_point"
}

# Function to create RAID array
create_raid() {
    local name=$1
    local level=$2
    local count=$3
    local size=$4
    
    echo -e "${BLUE}→${NC} Creating RAID$level array: $name"
    
    # Create images
    local raid_devices=""
    for i in $(seq 1 $count); do
        local img="${IMAGE_DIR}/raid_${name}_${i}.img"
        dd if=/dev/zero of="$img" bs=1M count="$size" status=progress
        local loop_dev=$(losetup -f --show "$img")
        raid_devices="$raid_devices $loop_dev"
    done
    
    # Create RAID array
    echo -e "${BLUE}→${NC} Creating RAID$level with devices: $raid_devices"
    mdadm --create "/dev/md/${name}" --level=$level --raid-devices=$count $raid_devices
    
    # Format
    mkfs.ext4 "/dev/md/${name}"
    
    # Mount
    local mount_point="${MOUNT_BASE}/${name}_raid"
    mkdir -p "$mount_point"
    mount "/dev/md/${name}" "$mount_point"
    
    echo -e "${GREEN}✓${NC} RAID$level array created and mounted to $mount_point"
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Loop Device Management Script${NC}

Usage: $0 <command> [options]

Commands:
  ${GREEN}create${NC} <name> <size>         - Create disk image
  ${GREEN}format${NC} <image> [fs_type]    - Format image (ext4, xfs, vfat)
  ${GREEN}mount${NC} <image> [mountpoint]  - Mount image
  ${GREEN}mount-iso${NC} <iso> [mountpoint] - Mount ISO file
  ${GREEN}umount${NC} <mountpoint>         - Unmount image
  ${GREEN}list${NC}                        - List mounted images
  ${GREEN}resize${NC} <image> <size>      - Resize image
  ${GREEN}encrypt${NC} <name> <size>      - Create encrypted image
  ${GREEN}mount-enc${NC} <image>          - Mount encrypted image
  ${GREEN}raid${NC} <name> <level> <count> <size> - Create RAID array
  ${GREEN}cleanup${NC}                    - Clean up all loop devices
  ${GREEN}help${NC}                       - Show this help

Examples:
  ${BLUE}# Create a 1GB disk image${NC}
  $0 create mydisk 1024
  
  ${BLUE}# Format as ext4${NC}
  $0 format ~/virtual-disk-images/mydisk.img
  
  ${BLUE}# Mount the image${NC}
  $0 mount ~/virtual-disk-images/mydisk.img /mnt/mydisk
  
  ${BLUE}# Mount an ISO${NC}
  $0 mount-iso ~/Downloads/ubuntu.iso
  
  ${BLUE}# Create encrypted image${NC}
  $0 encrypt secret 512
  
  ${BLUE}# Create RAID0 array with 3 disks${NC}
  $0 raid raid0 0 3 1024

EOF
}

# Function to cleanup
cleanup() {
    echo -e "${BLUE}→${NC} Cleaning up loop devices..."
    
    # Unmount all loop devices
    if [ -f /tmp/loop-mounts.txt ]; then
        while IFS=':' read -r loop mount image; do
            echo -e "${BLUE}→${NC} Unmounting: $mount"
            umount "$mount" 2>/dev/null || true
            losetup -d "$loop" 2>/dev/null || true
            rmdir "$mount" 2>/dev/null || true
        done < /tmp/loop-mounts.txt
        rm /tmp/loop-mounts.txt
    fi
    
    # Detach any remaining loop devices
    for dev in /dev/loop*; do
        if [[ "$dev" != /dev/loop-control ]]; then
            losetup -d "$dev" 2>/dev/null || true
        fi
    done
    
    # Close any encrypted devices
    for dev in /dev/mapper/*_enc; do
        if [ -e "$dev" ]; then
            name=$(basename "$dev" _enc)
            cryptsetup close "$name" 2>/dev/null || true
        fi
    done
    
    echo -e "${GREEN}✓${NC} Cleanup complete"
}

# Main function
main() {
    # Check for root
    check_root
    
    # Create image directory
    create_image_dir
    
    # Parse command
    case $1 in
        create)
            if [ $# -lt 3 ]; then
                echo -e "${RED}✗${NC} Usage: $0 create <name> <size_mb>"
                exit 1
            fi
            create_image "$2" "$3"
            ;;
        
        format)
            if [ $# -lt 2 ]; then
                echo -e "${RED}✗${NC} Usage: $0 format <image> [fs_type]"
                exit 1
            fi
            format_image "$2" "${3:-ext4}"
            ;;
        
        mount)
            if [ $# -lt 2 ]; then
                echo -e "${RED}✗${NC} Usage: $0 mount <image> [mountpoint]"
                exit 1
            fi
            mount_image "$2" "$3"
            ;;
        
        mount-iso)
            if [ $# -lt 2 ]; then
                echo -e "${RED}✗${NC} Usage: $0 mount-iso <iso> [mountpoint]"
                exit 1
            fi
            mount_iso "$2" "$3"
            ;;
        
        umount)
            if [ $# -lt 2 ]; then
                echo -e "${RED}✗${NC} Usage: $0 umount <mountpoint>"
                exit 1
            fi
            unmount_image "$2"
            ;;
        
        list|status)
            show_mounted
            ;;
        
        resize)
            if [ $# -lt 3 ]; then
                echo -e "${RED}✗${NC} Usage: $0 resize <image> <size_mb>"
                exit 1
            fi
            resize_image "$2" "$3"
            ;;
        
        encrypt)
            if [ $# -lt 3 ]; then
                echo -e "${RED}✗${NC} Usage: $0 encrypt <name> <size_mb>"
                exit 1
            fi
            create_encrypted_image "$2" "$3"
            ;;
        
        mount-enc)
            if [ $# -lt 2 ]; then
                echo -e "${RED}✗${NC} Usage: $0 mount-enc <image> [mountpoint]"
                exit 1
            fi
            mount_encrypted "$2" "$3"
            ;;
        
        raid)
            if [ $# -lt 5 ]; then
                echo -e "${RED}✗${NC} Usage: $0 raid <name> <level> <count> <size_mb>"
                exit 1
            fi
            create_raid "$2" "$3" "$4" "$5"
            ;;
        
        cleanup)
            cleanup
            ;;
        
        help|--help|-h)
            show_usage
            ;;
        
        *)
            echo -e "${RED}✗${NC} Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Trap signals
trap cleanup EXIT INT TERM

# Execute main
main "$@"

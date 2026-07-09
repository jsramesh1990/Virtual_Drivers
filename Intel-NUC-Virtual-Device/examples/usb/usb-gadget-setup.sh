#!/bin/bash
# usb-gadget-setup.sh - Setup USB gadget for device emulation

set -e

echo "========================================="
echo "USB Gadget Setup"
echo "========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
GADGET_DIR="/sys/kernel/config/usb_gadget"
GADGET_NAME="g1"
VENDOR_ID="0x1d6b"  # Linux Foundation
PRODUCT_ID="0x0104"  # Multifunction Composite Gadget
SERIAL="1234567890"
MANUFACTURER="Intel NUC"
PRODUCT="Virtual USB Gadget"

# Function to check if configfs is mounted
check_configfs() {
    if [ ! -d "/sys/kernel/config" ]; then
        echo -e "${RED}✗${NC} ConfigFS not mounted"
        echo "Mounting configfs..."
        sudo mount -t configfs none /sys/kernel/config
    fi
    echo -e "${GREEN}✓${NC} ConfigFS available"
}

# Function to load required modules
load_modules() {
    echo "Loading USB gadget modules..."
    
    sudo modprobe libcomposite
    sudo modprobe usb_f_acm
    sudo modprobe usb_f_ecm
    sudo modprobe usb_f_mass_storage
    sudo modprobe usb_f_hid
    sudo modprobe usb_f_uvc
    
    echo -e "${GREEN}✓${NC} Modules loaded"
}

# Function to create gadget
create_gadget() {
    echo "Creating USB gadget: $GADGET_NAME"
    
    cd $GADGET_DIR
    
    # Create gadget
    mkdir -p $GADGET_NAME
    cd $GADGET_NAME
    
    # Set IDs
    echo $VENDOR_ID > idVendor
    echo $PRODUCT_ID > idProduct
    
    # Set strings
    mkdir -p strings/0x409
    echo $SERIAL > strings/0x409/serialnumber
    echo $MANUFACTURER > strings/0x409/manufacturer
    echo $PRODUCT > strings/0x409/product
    
    echo -e "${GREEN}✓${GADGET_NAME}${NC} gadget created"
}

# Function to add serial function
add_serial_function() {
    echo "Adding serial function..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p functions/acm.usb0
    echo "Serial gadget" > functions/acm.usb0/name
    
    echo -e "${GREEN}✓${NC} Serial function added"
}

# Function to add ethernet function
add_ethernet_function() {
    echo "Adding ethernet function..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p functions/ecm.usb0
    echo "Ethernet gadget" > functions/ecm.usb0/name
    echo "00:11:22:33:44:55" > functions/ecm.usb0/dev_addr
    echo "00:11:22:33:44:56" > functions/ecm.usb0/host_addr
    
    echo -e "${GREEN}✓${NC} Ethernet function added"
}

# Function to add mass storage function
add_mass_storage_function() {
    echo "Adding mass storage function..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p functions/mass_storage.usb0
    echo "Mass Storage" > functions/mass_storage.usb0/name
    
    # Create storage image
    if [ ! -f /tmp/usb_storage.img ]; then
        echo "Creating storage image..."
        dd if=/dev/zero of=/tmp/usb_storage.img bs=1M count=64
        mkfs.ext4 /tmp/usb_storage.img
    fi
    
    echo "/tmp/usb_storage.img" > functions/mass_storage.usb0/lun.0/file
    echo "1" > functions/mass_storage.usb0/lun.0/removable
    echo "0" > functions/mass_storage.usb0/lun.0/ro
    
    echo -e "${GREEN}✓${NC} Mass storage function added"
}

# Function to add HID function
add_hid_function() {
    echo "Adding HID function..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p functions/hid.usb0
    echo 1 > functions/hid.usb0/protocol
    echo 1 > functions/hid.usb0/subclass
    echo 8 > functions/hid.usb0/report_length
    
    # Keyboard report descriptor
    echo -ne "\\x05\\x01\\x09\\x06\\xA1\\x01\\x05\\x07\\x19\\xE0\\x29\\xE7\\x15\\x00\\x25\\x01\\x75\\x01\\x95\\x08\\x81\\x02\\x95\\x01\\x75\\x08\\x81\\x01\\x95\\x05\\x75\\x01\\x05\\x08\\x19\\x01\\x29\\x05\\x91\\x02\\x95\\x01\\x75\\x03\\x91\\x01\\x95\\x06\\x75\\x08\\x15\\x00\\x25\\x65\\x05\\x07\\x19\\x00\\x29\\x65\\x81\\x00\\xC0" > functions/hid.usb0/report_desc
    
    echo -e "${GREEN}✓${NC} HID function added"
}

# Function to add UVC function
add_uvc_function() {
    echo "Adding UVC function..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p functions/uvc.usb0
    echo "UVC Camera" > functions/uvc.usb0/name
    
    # Configure UVC
    mkdir -p functions/uvc.usb0/control/header/h
    ln -s functions/uvc.usb0/control/header/h functions/uvc.usb0/control/class/fs
    ln -s functions/uvc.usb0/control/header/h functions/uvc.usb0/control/class/ss
    
    # Set streaming formats
    mkdir -p functions/uvc.usb0/streaming/header/h
    mkdir -p functions/uvc.usb0/streaming/uncompressed/u
    echo 1920 > functions/uvc.usb0/streaming/uncompressed/u/wWidth
    echo 1080 > functions/uvc.usb0/streaming/uncompressed/u/wHeight
    echo 30000000 > functions/uvc.usb0/streaming/uncompressed/u/dwMinBitRate
    echo 30000000 > functions/uvc.usb0/streaming/uncompressed/u/dwMaxBitRate
    echo 30 > functions/uvc.usb0/streaming/uncompressed/u/dwMaxVideoFrameBufferSize
    echo 0 > functions/uvc.usb0/streaming/uncompressed/u/bFormatIndex
    echo -ne "\\x00\\x00\\x00\\x00" > functions/uvc.usb0/streaming/uncompressed/u/guidFormat
    
    echo -e "${GREEN}✓${NC} UVC function added"
}

# Function to create configuration
create_config() {
    echo "Creating configuration..."
    
    cd $GADGET_DIR/$GADGET_NAME
    
    mkdir -p configs/c.1
    echo 500 > configs/c.1/MaxPower
    
    # Link functions to configuration
    ln -s functions/acm.usb0 configs/c.1/
    ln -s functions/ecm.usb0 configs/c.1/
    ln -s functions/mass_storage.usb0 configs/c.1/
    ln -s functions/hid.usb0 configs/c.1/
    ln -s functions/uvc.usb0 configs/c.1/
    
    # Set configuration strings
    mkdir -p configs/c.1/strings/0x409
    echo "Composite Gadget" > configs/c.1/strings/0x409/configuration
    
    echo -e "${GREEN}✓${NC} Configuration created"
}

# Function to enable gadget
enable_gadget() {
    echo "Enabling gadget..."
    
    UDC=$(ls /sys/class/udc/)
    if [ -z "$UDC" ]; then
        echo -e "${RED}✗${NC} No UDC found"
        return 1
    fi
    
    cd $GADGET_DIR/$GADGET_NAME
    echo $UDC > UDC
    
    echo -e "${GREEN}✓${NC} Gadget enabled on $UDC"
}

# Function to disable gadget
disable_gadget() {
    echo "Disabling gadget..."
    
    cd $GADGET_DIR/$GADGET_NAME
    echo "" > UDC 2>/dev/null || true
    
    echo -e "${GREEN}✓${NC} Gadget disabled"
}

# Function to remove gadget
remove_gadget() {
    echo "Removing gadget..."
    
    disable_gadget
    
    cd $GADGET_DIR/$GADGET_NAME
    
    # Remove function links
    rm -f configs/c.1/acm.usb0 2>/dev/null || true
    rm -f configs/c.1/ecm.usb0 2>/dev/null || true
    rm -f configs/c.1/mass_storage.usb0 2>/dev/null || true
    rm -f configs/c.1/hid.usb0 2>/dev/null || true
    rm -f configs/c.1/uvc.usb0 2>/dev/null || true
    
    # Remove configuration
    rm -rf configs/c.1 2>/dev/null || true
    
    # Remove functions
    rm -rf functions/acm.usb0 2>/dev/null || true
    rm -rf functions/ecm.usb0 2>/dev/null || true
    rm -rf functions/mass_storage.usb0 2>/dev/null || true
    rm -rf functions/hid.usb0 2>/dev/null || true
    rm -rf functions/uvc.usb0 2>/dev/null || true
    
    # Remove strings
    rm -rf strings/0x409 2>/dev/null || true
    
    cd $GADGET_DIR
    rmdir $GADGET_NAME 2>/dev/null || true
    
    echo -e "${GREEN}✓${NC} Gadget removed"
}

# Function to show gadget status
show_status() {
    echo "========================================="
    echo "USB Gadget Status"
    echo "========================================="
    echo ""
    
    if [ -d "$GADGET_DIR/$GADGET_NAME" ]; then
        echo -e "${GREEN}✓${NC} Gadget exists: $GADGET_NAME"
        echo ""
        echo "Functions:"
        ls $GADGET_DIR/$GADGET_NAME/functions/ 2>/dev/null || echo "  None"
        echo ""
        echo "Configuration:"
        ls $GADGET_DIR/$GADGET_NAME/configs/ 2>/dev/null || echo "  None"
        echo ""
        
        # Check if enabled
        UDC=$(cat $GADGET_DIR/$GADGET_NAME/UDC 2>/dev/null)
        if [ -n "$UDC" ]; then
            echo -e "${GREEN}✓${NC} Enabled on: $UDC"
        else
            echo -e "${YELLOW}⚠${NC} Not enabled"
        fi
    else
        echo -e "${YELLOW}⚠${NC} Gadget not created"
    fi
    
    echo ""
    echo "USB devices:"
    lsusb
}

# Main function
main() {
    case $1 in
        create)
            check_configfs
            load_modules
            create_gadget
            add_serial_function
            add_ethernet_function
            add_mass_storage_function
            add_hid_function
            add_uvc_function
            create_config
            enable_gadget
            echo ""
            echo -e "${GREEN}✓${NC} USB gadget created and enabled"
            ;;
        enable)
            enable_gadget
            ;;
        disable)
            disable_gadget
            ;;
        remove)
            remove_gadget
            ;;
        status)
            show_status
            ;;
        test)
            echo "Testing USB gadget..."
            echo ""
            echo "1. Checking serial port:"
            ls -la /dev/ttyGS* 2>/dev/null || echo "  No serial port"
            echo ""
            echo "2. Checking ethernet:"
            ip addr show usb0 2>/dev/null || echo "  No ethernet interface"
            echo ""
            echo "3. Checking mass storage:"
            ls -la /dev/sd* 2>/dev/null || echo "  No storage device"
            echo ""
            echo "4. Checking HID:"
            ls -la /dev/hidg* 2>/dev/null || echo "  No HID device"
            echo ""
            echo "5. Checking UVC:"
            ls -la /dev/video* 2>/dev/null || echo "  No video device"
            ;;
        *)
            echo "Usage: $0 {create|enable|disable|remove|status|test}"
            echo ""
            echo "Commands:"
            echo "  create  - Create and enable USB gadget"
            echo "  enable  - Enable existing USB gadget"
            echo "  disable - Disable USB gadget"
            echo "  remove  - Remove USB gadget"
            echo "  status  - Show gadget status"
            echo "  test    - Test gadget functionality"
            ;;
    esac
}

# Execute main
main "$@"

#!/bin/bash
# bridge-setup.sh - Setup network bridge for VMs and containers

set -e

echo "========================================="
echo "Network Bridge Setup"
echo "========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to create bridge
create_bridge() {
    local br_name=$1
    local ip=$2
    local netmask=$3
    
    echo "Creating bridge: $br_name"
    
    # Create bridge
    sudo ip link add name $br_name type bridge
    check_status "Bridge created"
    
    # Set bridge up
    sudo ip link set $br_name up
    check_status "Bridge up"
    
    # Assign IP
    if [ -n "$ip" ] && [ -n "$netmask" ]; then
        sudo ip addr add $ip/$netmask dev $br_name
        check_status "IP assigned: $ip/$netmask"
    fi
    
    # Enable STP
    sudo brctl stp $br_name on
    check_status "STP enabled"
    
    # Show bridge info
    echo ""
    echo "Bridge $br_name:"
    brctl show $br_name
    echo ""
    ip addr show $br_name
}

# Function to add interface to bridge
add_to_bridge() {
    local br_name=$1
    local iface=$2
    
    echo "Adding $iface to bridge $br_name"
    
    # Bring interface down
    sudo ip link set $iface down
    check_status "Interface down"
    
    # Add to bridge
    sudo brctl addif $br_name $iface
    check_status "Added to bridge"
    
    # Bring interface up
    sudo ip link set $iface up
    check_status "Interface up"
    
    # Show bridge info
    echo ""
    brctl show $br_name
}

# Function to remove interface from bridge
remove_from_bridge() {
    local br_name=$1
    local iface=$2
    
    echo "Removing $iface from bridge $br_name"
    
    sudo brctl delif $br_name $iface
    check_status "Removed from bridge"
    
    echo ""
    brctl show $br_name
}

# Function to setup DHCP for bridge
setup_dhcp() {
    local br_name=$1
    
    echo "Setting up DHCP for $br_name"
    
    # Install dnsmasq if not installed
    if ! command -v dnsmasq &> /dev/null; then
        echo "Installing dnsmasq..."
        sudo apt-get install -y dnsmasq
    fi
    
    # Configure dnsmasq
    cat << EOF | sudo tee /etc/dnsmasq.d/$br_name.conf
interface=$br_name
dhcp-range=10.0.0.100,10.0.0.200,12h
dhcp-option=3,10.0.0.1
dhcp-option=6,8.8.8.8
EOF
    
    # Restart dnsmasq
    sudo systemctl restart dnsmasq
    check_status "DHCP configured"
}

# Function to create bridge for VMs
create_vm_bridge() {
    echo "Creating VM bridge..."
    
    # Create bridge
    create_bridge "br0" "10.0.0.1" "24"
    
    # Enable IP forwarding
    sudo sysctl -w net.ipv4.ip_forward=1
    check_status "IP forwarding enabled"
    
    # Setup NAT
    sudo iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
    sudo iptables -A FORWARD -i br0 -o eth0 -j ACCEPT
    sudo iptables -A FORWARD -i eth0 -o br0 -j ACCEPT
    check_status "NAT and forwarding rules added"
    
    echo ""
    echo "VM bridge configured: br0 (10.0.0.1/24)"
}

# Function to create bridge for containers
create_container_bridge() {
    echo "Creating container bridge..."
    
    # Create bridge
    create_bridge "br1" "172.17.0.1" "16"
    
    echo ""
    echo "Container bridge configured: br1 (172.17.0.1/16)"
}

# Function to show all bridges
show_bridges() {
    echo "All Bridges:"
    echo ""
    brctl show
    echo ""
    
    for br in $(brctl show | grep -v "bridge name" | awk '{print $1}'); do
        echo "Bridge $br:"
        ip addr show $br
        echo ""
    done
}

# Function to cleanup
cleanup() {
    echo "Cleaning up bridges..."
    
    # Remove all bridges
    for br in $(brctl show | grep -v "bridge name" | awk '{print $1}'); do
        if [ -n "$br" ]; then
            echo "Removing bridge $br"
            sudo ip link set $br down
            sudo brctl delbr $br 2>/dev/null || true
        fi
    done
    
    # Remove NAT rules
    sudo iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE 2>/dev/null || true
    sudo iptables -D FORWARD -i br0 -o eth0 -j ACCEPT 2>/dev/null || true
    sudo iptables -D FORWARD -i eth0 -o br0 -j ACCEPT 2>/dev/null || true
    
    # Remove dnsmasq config
    sudo rm -f /etc/dnsmasq.d/*.conf 2>/dev/null || true
    sudo systemctl restart dnsmasq
    
    echo "Cleanup complete"
}

# Main function
main() {
    case $1 in
        create)
            if [ $# -eq 3 ]; then
                create_bridge $2 $3 "24"
            elif [ $# -eq 4 ]; then
                create_bridge $2 $3 $4
            else
                create_bridge "br0" "10.0.0.1" "24"
            fi
            ;;
        add)
            if [ $# -eq 3 ]; then
                add_to_bridge $2 $3
            else
                echo "Usage: $0 add <bridge> <interface>"
            fi
            ;;
        remove)
            if [ $# -eq 3 ]; then
                remove_from_bridge $2 $3
            else
                echo "Usage: $0 remove <bridge> <interface>"
            fi
            ;;
        dhcp)
            if [ $# -eq 2 ]; then
                setup_dhcp $2
            else
                setup_dhcp "br0"
            fi
            ;;
        vm)
            create_vm_bridge
            ;;
        container)
            create_container_bridge
            ;;
        show)
            show_bridges
            ;;
        cleanup)
            cleanup
            ;;
        *)
            echo "Usage: $0 {create|add|remove|dhcp|vm|container|show|cleanup}"
            echo ""
            echo "Examples:"
            echo "  $0 create br0 10.0.0.1 24"
            echo "  $0 add br0 eth0"
            echo "  $0 remove br0 eth0"
            echo "  $0 dhcp br0"
            echo "  $0 vm"
            echo "  $0 container"
            echo "  $0 show"
            echo "  $0 cleanup"
            ;;
    esac
}

# Execute main
main "$@"

#!/bin/bash
# socat-example.sh - Socat serial bridge example

set -e

echo "========================================="
echo "Socat Serial Bridge Example"
echo "========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if socat is installed
if ! command -v socat &> /dev/null; then
    echo -e "${RED}✗${NC} socat not installed"
    echo "Install with: sudo apt install socat"
    exit 1
fi

# Function to create virtual serial ports
create_ports() {
    echo "Creating virtual serial ports..."
    
    # Create two linked PTYs
    socat -d -d PTY,link=/dev/ttyV0,raw,echo=0 PTY,link=/dev/ttyV1,raw,echo=0 &
    SOCAT_PID=$!
    
    sleep 2
    
    if [ -e /dev/ttyV0 ] && [ -e /dev/ttyV1 ]; then
        echo -e "${GREEN}✓${NC} Virtual serial ports created"
        echo "  /dev/ttyV0 <-> /dev/ttyV1"
    else
        echo -e "${RED}✗${NC} Failed to create virtual serial ports"
        kill $SOCAT_PID 2>/dev/null || true
        return 1
    fi
    
    # Save PID for cleanup
    echo $SOCAT_PID > /tmp/socat-example.pid
}

# Function to create TCP bridge
create_tcp_bridge() {
    local port=$1
    
    echo "Creating TCP bridge on port $port..."
    
    # Bridge serial port to TCP
    socat TCP-LISTEN:$port,reuseaddr,fork PTY,link=/dev/ttyV2,raw,echo=0 &
    TCP_PID=$!
    
    sleep 2
    
    if [ -e /dev/ttyV2 ]; then
        echo -e "${GREEN}✓${NC} TCP bridge created on port $port"
        echo "  Connect using: socat - TCP:localhost:$port"
    else
        echo -e "${RED}✗${NC} Failed to create TCP bridge"
        kill $TCP_PID 2>/dev/null || true
        return 1
    fi
    
    echo $TCP_PID >> /tmp/socat-example.pid
}

# Function to create UDP bridge
create_udp_bridge() {
    local port=$1
    
    echo "Creating UDP bridge on port $port..."
    
    # Bridge serial port to UDP
    socat UDP-LISTEN:$port,reuseaddr,fork PTY,link=/dev/ttyV3,raw,echo=0 &
    UDP_PID=$!
    
    sleep 2
    
    if [ -e /dev/ttyV3 ]; then
        echo -e "${GREEN}✓${NC} UDP bridge created on port $port"
        echo "  Connect using: socat - UDP:localhost:$port"
    else
        echo -e "${RED}✗${NC} Failed to create UDP bridge"
        kill $UDP_PID 2>/dev/null || true
        return 1
    fi
    
    echo $UDP_PID >> /tmp/socat-example.pid
}

# Function to create SSL bridge
create_ssl_bridge() {
    local port=$1
    
    echo "Creating SSL bridge on port $port..."
    
    # Generate certificate if needed
    if [ ! -f /tmp/server.pem ]; then
        echo "Generating SSL certificate..."
        openssl req -x509 -newkey rsa:2048 -nodes \
            -keyout /tmp/server.key \
            -out /tmp/server.crt \
            -days 365 \
            -subj "/CN=localhost"
        cat /tmp/server.crt /tmp/server.key > /tmp/server.pem
        chmod 600 /tmp/server.pem
    fi
    
    # Bridge serial port to SSL
    socat OPENSSL-LISTEN:$port,reuseaddr,fork,cert=/tmp/server.pem,verify=0 \
        PTY,link=/dev/ttyV4,raw,echo=0 &
    SSL_PID=$!
    
    sleep 2
    
    if [ -e /dev/ttyV4 ]; then
        echo -e "${GREEN}✓${NC} SSL bridge created on port $port"
        echo "  Connect using: socat - OPENSSL:localhost:$port,verify=0"
    else
        echo -e "${RED}✗${NC} Failed to create SSL bridge"
        kill $SSL_PID 2>/dev/null || true
        return 1
    fi
    
    echo $SSL_PID >> /tmp/socat-example.pid
}

# Function to test serial communication
test_communication() {
    echo "Testing serial communication..."
    
    # Write test data to first port
    echo "Test message from socat" > /dev/ttyV0
    
    # Read from second port
    sleep 1
    if cat /dev/ttyV1 2>/dev/null | grep -q "Test message"; then
        echo -e "${GREEN}✓${NC} Serial communication working"
    else
        echo -e "${RED}✗${NC} Serial communication failed"
    fi
}

# Function to show status
show_status() {
    echo ""
    echo "========================================="
    echo "Socat Bridge Status"
    echo "========================================="
    echo ""
    
    echo "Serial ports:"
    ls -la /dev/ttyV* 2>/dev/null || echo "  No virtual serial ports"
    echo ""
    
    echo "Running socat processes:"
    ps aux | grep socat | grep -v grep || echo "  No socat processes"
    echo ""
    
    echo "Listening ports:"
    netstat -tuln | grep -E "socat|:800[0-9]" || echo "  No listening ports"
    echo ""
    
    echo "PTY information:"
    ls -la /dev/pts/* 2>/dev/null | head -5
}

# Function to cleanup
cleanup() {
    echo "Cleaning up..."
    
    # Kill all socat processes
    if [ -f /tmp/socat-example.pid ]; then
        while read pid; do
            echo "Killing process $pid"
            kill $pid 2>/dev/null || true
        done < /tmp/socat-example.pid
        rm /tmp/socat-example.pid
    fi
    
    # Kill any remaining socat processes
    pkill socat 2>/dev/null || true
    
    # Remove virtual serial ports
    rm -f /dev/ttyV[0-9] 2>/dev/null || true
    
    echo "Cleanup complete"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  create    - Create virtual serial ports"
    echo "  tcp       - Create TCP bridge"
    echo "  udp       - Create UDP bridge"
    echo "  ssl       - Create SSL bridge"
    echo "  test      - Test serial communication"
    echo "  status    - Show current status"
    echo "  cleanup   - Clean up all bridges"
    echo ""
    echo "Examples:"
    echo "  $0 create      # Create virtual serial ports"
    echo "  $0 tcp 8000    # Create TCP bridge on port 8000"
    echo "  $0 test        # Test serial communication"
    echo "  $0 status      # Show status"
    echo "  $0 cleanup     # Clean up everything"
}

# Main function
main() {
    case $1 in
        create)
            create_ports
            test_communication
            show_status
            ;;
        tcp)
            port=${2:-8000}
            create_ports
            create_tcp_bridge $port
            show_status
            ;;
        udp)
            port=${2:-8001}
            create_ports
            create_udp_bridge $port
            show_status
            ;;
        ssl)
            port=${2:-8002}
            create_ports
            create_ssl_bridge $port
            show_status
            ;;
        test)
            test_communication
            ;;
        status)
            show_status
            ;;
        cleanup)
            cleanup
            ;;
        *)
            show_usage
            ;;
    esac
}

# Handle signals
trap cleanup EXIT INT TERM

# Execute main
main "$@"

echo ""
echo "========================================="
echo "Example Complete"
echo "========================================="
